<?php
function plugin_init_layananit()
{
    global $PLUGIN_HOOKS;
    $PLUGIN_HOOKS['csrf_compliant']['layananit'] = true;
    $PLUGIN_HOOKS['menu_toadd']['layananit'] = ['tools' => 'PluginLayananitMenu'];
}
function plugin_version_layananit()
{
    return ['name' => 'Layanan TI', 'version' => '0.1.0', 'author' => 'IT Helpdesk', 'license' => 'GPLv3+',
        'requirements' => ['glpi' => ['min' => '11.0.8', 'max' => '11.0.99']]];
}
