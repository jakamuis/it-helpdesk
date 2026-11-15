<?php
function plugin_init_itrequest()
{
    global $PLUGIN_HOOKS;
    // This one machine endpoint authenticates a scoped bearer token itself.
    Glpi\Http\Firewall::addPluginStrategyForLegacyScripts('itrequest', '#^/front/wa-feed\.php$#', Glpi\Http\Firewall::STRATEGY_NO_CHECK);
    $PLUGIN_HOOKS['helpdesk_menu_entry']['itrequest'] = '/front/index.php';
    $PLUGIN_HOOKS['helpdesk_menu_entry_icon']['itrequest'] = 'ti ti-clipboard-check';
    $PLUGIN_HOOKS['csrf_compliant']['itrequest'] = true;
    $PLUGIN_HOOKS['menu_toadd']['itrequest'] = ['tools' => 'PluginItrequestMenu'];
}
function plugin_version_itrequest()
{
    return ['name' => 'Request IT', 'version' => '0.3.0', 'author' => 'IT Helpdesk',
        'license' => 'GPLv3+', 'homepage' => '',
        'requirements' => ['glpi' => ['min' => '11.0.8', 'max' => '11.0.99']]];
}
