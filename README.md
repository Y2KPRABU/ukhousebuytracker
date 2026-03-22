# 🎈 Blank app template

A simple Streamlit app template for you to modify!

[![Open in Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://blank-app-template.streamlit.app/)

### How to run it on your own machine

1. Install the requirements

   ```
   $ pip install -r requirements.txt
   ```

2. Run the app

   ```
   $ streamlit run streamlit_app.py
   ```

### Phase 1: Account-Based Save (Default)

The app now keeps checklist persistence logic in a separate module: `cloud_storage.py`.

- Default behavior: account-based save/load in local JSON files under `.user_data/`.
- Optional cloud backend: Supabase REST (set environment variables below).

Optional environment variables for Supabase cloud save:

```
SUPABASE_URL=https://<project>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<service_role_key_or_anon_key>
SUPABASE_CHECKLIST_TABLE=user_checklists
USER_ID=<default_account_id>
```

Supabase DB setup:

1. Open `scripts/setup_supabase.sql`.
2. Run it in Supabase SQL Editor once for your project.

The sidebar includes `Account & Cloud Save` controls to load/save a specific account and enable autosave.

### Quick Env Setup

Local shell (bash/zsh/git-bash):

1. Run `scripts/setup_supabase.sql` once in Supabase SQL Editor.
1. Open `scripts/set_supabase_env.sh` and put your real values.
2. Run:

```
source scripts/set_supabase_env.sh
streamlit run streamlit_app.py
```

Streamlit Cloud:

1. Run `scripts/setup_supabase.sql` once in Supabase SQL Editor.
1. Open `.streamlit/secrets.toml.example`.
2. Copy its contents into your app's Streamlit Cloud Secrets UI.
3. Redeploy or reboot the app.

The app bootstraps these secrets into environment variables at startup.
