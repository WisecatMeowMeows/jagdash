import streamlit as st


def manifest():
    return {
        "name": "config_plugin",
        "version": "1.0",
        "provides": [],
        "requires": []
    }

# ============================================================
# GET UI CONTEXT
# ============================================================

def get_ui_context(context):
    from theme_engine import get_theme, preset_names
    profiles       = context.get_all_profiles()
    active_profile = context.get_active_profile()
    active_name    = profiles[0] if profiles else "default"
    news_key       = context.get_api_key("newsapi")
    theme          = get_theme(active_profile)
    return {
        "profiles":       profiles,
        "active_profile": active_profile,
        "active_name":    active_name,
        "news_key_set":   bool(news_key),
        "theme":          theme,
        "preset_names":   preset_names(),
    }
    
def render_ui(context):
    st.subheader("Dashboard Configuration")

    profile = context.get_active_profile()
    profiles = context.get_all_profiles()

    st.write("### Active Profile")

    selected_profile = st.selectbox(
        "Load Profile",
        profiles,
        index=profiles.index(
            context.get_active_profile()["dashboard_name"]
        ) if context.get_active_profile()["dashboard_name"] in profiles else 0
    )

    if st.button("Load Selected Profile"):
        context.set_active_profile(
            selected_profile
        )
        st.success("Profile loaded")
        st.rerun()

    st.write("### Create New Profile")

    new_profile_name = st.text_input(
        "New Profile Name"
    )

    if st.button("Create Profile"):
        if new_profile_name:
            context.create_profile(
                new_profile_name
            )
            st.success(
                "Profile created"
            )

    st.write("### Dashboard Settings")

    dashboard_name = st.text_input(
        "Dashboard Display Name",
        value=profile.get(
            "dashboard_name",
            "JagDash"
        )
    )

    logo_path = st.text_input(
        "Logo File Path",
        value=profile.get(
            "logo_path",
            ""
        )
    )

    theme = st.selectbox(
        "Theme",
        [
            "default",
            "dark",
            "light"
        ]
    )

    st.write(
        "(Advanced theme customization placeholder for later)"
    )

    
    st.write("### API Keys")

    current_news_key = context.get_api_key(
        "newsapi"
    )

    news_key = st.text_input(
        "NewsAPI Key",
        value=current_news_key,
        type="password"
    )

    
#-----------save settings button-------------------

    if st.button("Save Settings"):
        context.update_profile_value(
            "dashboard_name",
            dashboard_name
        )

        context.update_profile_value(
            "logo_path",
            logo_path
        )

        context.update_profile_value(
            "theme",
            theme
        )

        context.update_api_key(
            "newsapi",
            news_key
)

        st.success(
            "Settings saved"
        )
        st.rerun()