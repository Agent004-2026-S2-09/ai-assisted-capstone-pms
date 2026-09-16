Checked the deployment details in Streamlit:

Setting	Value
Repository	Agent004-2026-S2-09/ai-assisted-capstone-pms
Branch	main
Main file	app.py
Opened the repository’s deploy-key settings.
GitHub displayed “Disabled by Agent004-2026-S2-09”, confirming that an organisation policy blocked deploy keys.
Opened the organisation’s settings:
Agent004-2026-S2-09 → Settings → Member privileges.
Enabled deploy keys.
Located Deploy keys, selected Enabled, and clicked Save. This setting is under organisation Member privileges, not repository Actions → Policies.
Returned to Streamlit and retried deployment/rebooted the app.
Confirmed the application loaded successfully.