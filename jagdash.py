import streamlit as st
from host import PluginHost
from plugin_loader import load_plugins
from plugin_context import PluginContext



# ----------------------------------------
# Initialize Host
# ----------------------------------------
@st.cache_resource
def initialize_host():
    host = PluginHost()

    plugins = load_plugins()

    for plugin in plugins:
        host.register_plugin(plugin)

    return host


# ----------------------------------------
# Main Application
# ----------------------------------------
def main():
    st.set_page_config(
        page_title="JagDash",
        layout="wide"
    )

    host = initialize_host()

    # ----------------------------------------
    # Dependency Validation
    # ----------------------------------------
    dependency_issues = host.validate_dependencies()

    if dependency_issues:
        st.error("Dependency issues detected")
        st.json(dependency_issues)
        st.stop()

    # ----------------------------------------
    # Initialize session state
    # ----------------------------------------
    if "selected_plugin" not in st.session_state:
        st.session_state.selected_plugin = None

    # ----------------------------------------
    # Header
    # ----------------------------------------
    profile = host.get_active_profile()

    dashboard_name = profile.get(
        "dashboard_name",
        "JagDash"
    )

    logo_path = profile.get(
        "logo_path",
        ""
    )

    if logo_path:
        try:
            st.sidebar.image(
                logo_path,
                width=100
            )
        except:
            pass

    st.title(dashboard_name)


    # ----------------------------------------
    # Sidebar Plugin Launcher
    # ----------------------------------------
    st.sidebar.title("Plugins")

    for plugin_name in host.list_plugins():

        enabled_key = f"enabled_{plugin_name}"

        profile_plugins = profile.get(
            "plugins",
            {}
        )

        saved_state = profile_plugins.get(
            plugin_name,
            {}
        ).get(
            "enabled",
            True
        )

        # initialize session state only once
        if enabled_key not in st.session_state:
            st.session_state[enabled_key] = saved_state

        # ALWAYS create columns every loop iteration
        col1, col2 = st.sidebar.columns([4, 1])

        # Launch button
        with col1:
            if st.button(
                plugin_name,
                key=f"launch_{plugin_name}",
                use_container_width=True
            ):
                st.session_state.selected_plugin = plugin_name

        # Enable/disable checkbox
        with col2:
            enabled_value = st.checkbox(
                f"Enable {plugin_name}",
                key=enabled_key,
                label_visibility="collapsed"
            )

            host.update_plugin_state(
                plugin_name,
                enabled_value
            )

    selected_plugin = st.session_state.selected_plugin

    # ----------------------------------------
    # Main Plugin Render Area
    # ----------------------------------------
    st.divider()

    if selected_plugin is not None:

        enabled_key = f"enabled_{selected_plugin}"

        if not st.session_state.get(enabled_key, True):
            st.warning(
                f"{selected_plugin} is currently disabled."
            )

        else:
            plugin_data = host.plugins[selected_plugin]
            plugin_module = plugin_data["module"]

            if hasattr(plugin_module, "render_ui"):
                st.subheader(
                    f"{selected_plugin} Interface"
                )

                context = PluginContext(host)

                try:
                    plugin_module.render_ui(context)

                except Exception as e:
                    st.error(
                        f"Plugin execution failed: {e}"
                    )

            else:
                st.info(
                    f"{selected_plugin} has no UI panel."
                )

    else:
        st.info(
            "Select a plugin from the sidebar."
        )

    # ----------------------------------------
    # Diagnostics Tabs
    # ----------------------------------------
    st.divider()

    tab1, tab2, tab3, tab4 = st.tabs([
        "Registry",
        "Capabilities",
        "Request Logs",
        "Event Logs"
    ])

    with tab1:
        st.subheader("Plugin Registry")
        st.json(
            host.get_manifests()
        )

    with tab2:
        st.subheader("Capabilities")
        st.write(
            host.list_capabilities()
        )

    with tab3:
        st.subheader("Request Logs")
        st.json(
            host.get_logs()
        )

    with tab4:
        st.subheader("Event Logs")
        st.json(
            host.get_event_log()
        )


if __name__ == "__main__":
    main()