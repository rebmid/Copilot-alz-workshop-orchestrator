import requests

ALZ_CHECKLIST_URL = "https://raw.githubusercontent.com/Azure/review-checklists/main/checklists/alz_checklist.en.json"

def load_alz_checklist():
    response = requests.get(ALZ_CHECKLIST_URL)
    response.raise_for_status()
    return response.json()
