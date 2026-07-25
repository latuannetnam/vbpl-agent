"""
Automated script to drop OpenSearch vector index for the VBPL connector
and trigger full offline re-indexing using pre-exported release data.

Utilizes configuration variables defined in .env (via vbpl_kb.config.Settings).
"""
import sys
import time
import httpx
from vbpl_kb.config import Settings
from vbpl_kb.connector_control import OnyxConnectorClient, ConnectorControlError


def get_host_base_url(settings: Settings) -> str:
    url = settings.onyx_base_url
    if "api_server" in url or "localhost" in url:
        return "http://127.0.0.1:8080"
    return url


def main() -> None:
    settings = Settings()
    if "api_server" in settings.onyx_base_url or "localhost" in settings.onyx_base_url:
        settings.onyx_base_url = "http://127.0.0.1:8080"
    base_url = settings.onyx_base_url
    connector_id = settings.onyx_connector_id or 1

    headers = {}
    api_key = settings.onyx_api_key.get_secret_value()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    print(f"=== Onyx Vector Index Reset & Re-index Utility ===")
    print(f"Onyx Base URL: {base_url}")
    print(f"Connector ID: {connector_id}")

    # 1. Inspect existing CC Pairs
    with httpx.Client(timeout=30.0) as client:
        try:
            conn_resp = client.get(f"{base_url}/manage/admin/connector", headers=headers)
            conn_resp.raise_for_status()
            connectors = conn_resp.json()
            target_conn = next((c for c in connectors if c.get("id") == connector_id), None)
            
            if not target_conn:
                print(f"Connector ID {connector_id} not found. Creating new connector...")
                control = OnyxConnectorClient(settings)
                connector_id = control.create_connector("VBPL Export")
                credential_id = 2
            else:
                cred_ids = target_conn.get("credential_ids", [])
                credential_id = cred_ids[0] if cred_ids else 2

            print(f"Target Connector ID: {connector_id}, Credential ID: {credential_id}")

            # 2. Trigger CC Pair deletion to drop OpenSearch index & metadata
            print("\n[Step 1/3] Triggering CC Pair deletion & OpenSearch index purge...")
            del_resp = client.post(
                f"{base_url}/manage/admin/deletion-attempt",
                json={"connector_id": connector_id, "credential_id": credential_id},
                headers=headers,
            )
            del_resp.raise_for_status()
            print("Deletion attempt initiated successfully.")

            # Poll for deletion completion if CC pair exists
            print("Waiting for background deletion task to complete...")
            for _ in range(60):
                status_resp = client.get(f"{base_url}/manage/admin/cc-pair/{credential_id}", headers=headers)
                if status_resp.status_code in (404, 400):
                    print("CC Pair deletion completed.")
                    break
                if status_resp.status_code == 200:
                    pair_data = status_resp.json()
                    st = pair_data.get("status")
                    docs_left = pair_data.get("num_docs_indexed", 0)
                    print(f"Deletion status: {st} (Docs remaining: {docs_left})...")
                    if st not in ("DELETING", "DELETION_IN_PROGRESS"):
                        print("CC Pair deletion finished.")
                        break
                time.sleep(4.0)

        except Exception as e:
            print(f"Warning/Note during deletion trigger: {e}")

    # 3. Ensure connector setup is active
    print("\n[Step 2/3] Verifying connector & credential binding...")
    control_client = OnyxConnectorClient(settings)
    active_connector_id = control_client.create_connector("VBPL Export")
    print(f"Active Connector ID: {active_connector_id}")

    # 4. Trigger full re-indexing from beginning using exported data
    print("\n[Step 3/3] Triggering full re-indexing from pre-exported active release (--from-beginning)...")
    try:
        attempt_id = control_client.trigger(active_connector_id, from_beginning=True)
        print(f"Re-indexing triggered successfully! Index Attempt ID: {attempt_id}")
        
        print("\nMonitoring re-indexing progress...")
        final_status = control_client.wait_for_indexed(active_connector_id, timeout_seconds=settings.onyx_connector_timeout_seconds)
        print(f"\nRe-indexing Finished! Status: {final_status.last_status}, Total Chunks: {final_status.total_chunks}")
        print("==================================================")
        print("Onyx index reset & re-index completed successfully!")

    except ConnectorControlError as cce:
        print(f"Connector Control Error: {cce}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
