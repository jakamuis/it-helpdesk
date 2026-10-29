<?php
function plugin_providersla_install()
{
    global $DB;
    $DB->doQuery("CREATE TABLE IF NOT EXISTS `glpi_plugin_providersla_episodes` (
        `id` int unsigned NOT NULL AUTO_INCREMENT,
        `tickets_id` int unsigned NOT NULL,
        `entities_id` int unsigned NOT NULL,
        `open_ticket_id` int unsigned DEFAULT NULL,
        `suppliers_id` int unsigned NOT NULL DEFAULT 0,
        `provider_name` varchar(255) NOT NULL,
        `circuit` varchar(255) NOT NULL DEFAULT '',
        `customer_sid` varchar(255) NOT NULL DEFAULT '',
        `reference` varchar(255) NOT NULL DEFAULT '',
        `transferred_epoch` bigint unsigned NOT NULL,
        `restored_epoch` bigint unsigned DEFAULT NULL,
        `verified_epoch` bigint unsigned DEFAULT NULL,
        `target_seconds` int unsigned DEFAULT NULL,
        `transfer_evidence` text NOT NULL,
        `recovery_evidence` text DEFAULT NULL,
        `users_id_start` int unsigned NOT NULL,
        `users_id_end` int unsigned DEFAULT NULL,
        `previous_status` int NOT NULL,
        `paused_by_plugin` tinyint NOT NULL DEFAULT 0,
        `is_void` tinyint NOT NULL DEFAULT 0,
        `created_epoch` bigint unsigned NOT NULL,
        PRIMARY KEY (`id`), UNIQUE KEY `one_open_episode` (`open_ticket_id`),
        KEY `ticket_history` (`tickets_id`, `transferred_epoch`),
        KEY `entity_start` (`entities_id`, `transferred_epoch`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci");
    if (!$DB->fieldExists('glpi_plugin_providersla_episodes', 'customer_sid')) {
        $DB->doQuery("ALTER TABLE `glpi_plugin_providersla_episodes` ADD `customer_sid` varchar(255) NOT NULL DEFAULT ''");
    }
    $DB->doQuery("CREATE TABLE IF NOT EXISTS `glpi_plugin_providersla_events` (
        `id` int unsigned NOT NULL AUTO_INCREMENT,
        `episodes_id` int unsigned NOT NULL,
        `tickets_id` int unsigned NOT NULL,
        `users_id` int unsigned NOT NULL,
        `event_epoch` bigint unsigned NOT NULL,
        `action` varchar(20) NOT NULL,
        `details` text NOT NULL,
        PRIMARY KEY (`id`), KEY `episode_history` (`episodes_id`, `id`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci");
    return true;
}
function plugin_providersla_uninstall()
{
    // Preserve SLA evidence and audit history on uninstall. No core data is removed.
    return true;
}
