# collectors/azure_client.py
from __future__ import annotations
import os
import time
import requests
from dataclasses import dataclass
from typing import Any, Dict, Optional
from azure.identity import AzureCliCredential

ARM = "https://management.azure.com"

@dataclass
class AzureClient:
    credential: AzureCliCredential
    subscription_id: Optional[str] = None
    _token: Optional[str] = None
    _token_expires: float = 0.0

    def token(self) -> str:
        now = time.time()
        if self._token and now < self._token_expires - 60:
            return self._token
        access_token = self.credential.get_token(f"{ARM}/.default")
        self._token = access_token.token
        self._token_expires = access_token.expires_on
        return self._token

    def get(self, path: str, api_version: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = f"{ARM}{path}"
        qp = {"api-version": api_version}
        if params:
            qp.update(params)

        headers = {"Authorization": f"Bearer {self.token()}"}

        # simple retry for throttles
        for attempt in range(5):
            r = requests.get(url, headers=headers, params=qp, timeout=60)
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(1.5 * (attempt + 1))
                continue
            r.raise_for_status()
            return r.json()

        r.raise_for_status()
        return r.json()

    def post(self, path: str, api_version: str, body: Optional[Dict[str, Any]] = None, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = f"{ARM}{path}"
        qp = {"api-version": api_version}
        if params:
            qp.update(params)

        headers = {"Authorization": f"Bearer {self.token()}", "Content-Type": "application/json"}

        for attempt in range(5):
            r = requests.post(url, headers=headers, params=qp, json=body or {}, timeout=60)
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(1.5 * (attempt + 1))
                continue
            r.raise_for_status()
            return r.json()

        r.raise_for_status()
        return r.json()

def build_client(subscription_id: Optional[str] = None) -> AzureClient:
    cred = AzureCliCredential(process_timeout=30)
    return AzureClient(credential=cred, subscription_id=subscription_id)


GRAPH = "https://graph.microsoft.com"


@dataclass
class GraphClient:
    """Lightweight client for Microsoft Graph API (/beta and /v1.0)."""
    credential: AzureCliCredential
    _token: Optional[str] = None
    _token_expires: float = 0.0

    def token(self) -> str:
        now = time.time()
        if self._token and now < self._token_expires - 60:
            return self._token
        access_token = self.credential.get_token(f"{GRAPH}/.default")
        self._token = access_token.token
        self._token_expires = access_token.expires_on
        return self._token

    def get(self, path: str, params: Optional[Dict[str, Any]] = None, *, api: str = "beta") -> Dict[str, Any]:
        url = f"{GRAPH}/{api}{path}"
        headers = {"Authorization": f"Bearer {self.token()}"}
        for attempt in range(5):
            r = requests.get(url, headers=headers, params=params or {}, timeout=60)
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(1.5 * (attempt + 1))
                continue
            r.raise_for_status()
            return r.json()
        r.raise_for_status()
        return r.json()

    def get_all(self, path: str, params: Optional[Dict[str, Any]] = None, *, api: str = "beta", max_pages: int = 10) -> list:
        """Follow @odata.nextLink for paged results."""
        items: list = []
        url = f"{GRAPH}/{api}{path}"
        headers = {"Authorization": f"Bearer {self.token()}"}
        page = 0
        while url and page < max_pages:
            for attempt in range(5):
                r = requests.get(url, headers=headers, params=params if page == 0 else None, timeout=60)
                if r.status_code in (429, 500, 502, 503, 504):
                    time.sleep(1.5 * (attempt + 1))
                    continue
                r.raise_for_status()
                data = r.json()
                items.extend(data.get("value", []))
                url = data.get("@odata.nextLink", "")
                break
            else:
                r.raise_for_status()
            page += 1
            params = None  # nextLink already contains query params
        return items


def build_graph_client() -> GraphClient:
    cred = AzureCliCredential(process_timeout=30)
    return GraphClient(credential=cred)
