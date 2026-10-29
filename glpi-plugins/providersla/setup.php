<?php
/** Manual Helpdesk/provider SLA split for GLPI 11. GPL-3.0-or-later. */
function plugin_init_providersla()
{
    global $PLUGIN_HOOKS;
    $PLUGIN_HOOKS['csrf_compliant']['providersla'] = true;
    Plugin::registerClass('PluginProviderslaTicket', ['addtabon' => ['Ticket']]);
    $PLUGIN_HOOKS['pre_itil_info_section']['providersla'] = ['PluginProviderslaSidebar', 'show'];
    $PLUGIN_HOOKS['add_javascript']['providersla'] = ['js/sidebar.js'];
    $PLUGIN_HOOKS['add_css']['providersla'] = ['css/sidebar.css'];
    if (Session::haveRight('ticket', UPDATE)) {
        $PLUGIN_HOOKS['menu_toadd']['providersla'] = ['tools' => 'PluginProviderslaTicket'];
    }
}
function plugin_version_providersla()
{
    return ['name' => 'SLA Provider', 'version' => '1.2.0', 'author' => 'IT Helpdesk',
        'license' => 'GPLv3+', 'homepage' => '',
        'requirements' => ['glpi' => ['min' => '11.0.8', 'max' => '11.0.99']]];
}
