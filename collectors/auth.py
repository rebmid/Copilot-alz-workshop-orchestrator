from azure.identity import AzureCliCredential

ARM_SCOPE = "https://management.azure.com/.default"

_credential = None

def get_credential():
    global _credential
    if _credential is None:
        _credential = AzureCliCredential(process_timeout=30)
    return _credential

def get_arm_token() -> str:
    cred = get_credential()
    return cred.get_token(ARM_SCOPE).token
