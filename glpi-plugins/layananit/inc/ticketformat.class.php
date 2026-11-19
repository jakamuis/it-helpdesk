<?php

class PluginLayananitTicketFormat
{
    public static function plain(string $value): string
    {
        return trim(preg_replace('/\s+/u', ' ', html_entity_decode(strip_tags($value), ENT_QUOTES | ENT_HTML5, 'UTF-8')) ?? '');
    }

    public static function portalFields(int $requester, string $site, string $subject, string $report): array
    {
        $name = self::plain((string) getUserName($requester));
        $site = self::plain($site);
        $subject = self::plain($subject);
        if ($site === '' && preg_match('/\b(?:di|cabang|lokasi)[: ]+(?:kantor\s+)?((?:SIG|SGI)\s+[\p{L}\p{N}]+|HO)\b/iu', "$subject $report", $match)) {
            $site = $match[1];
        }
        if ($site !== '') {
            $subject = preg_replace('/\s+(?:di|cabang|lokasi)[: ]+(?:kantor\s+)?' . preg_quote($site, '/') . '[. ]*$/iu', '', $subject) ?: $subject;
        }
        $subject = $subject ?: self::plain($report);
        return [
            'name' => mb_substr(str_replace(' - ', ' – ', $name ?: 'Pelapor belum diketahui'), 0, 65),
            'site' => $site ?: 'Cabang belum diketahui',
            'summary' => mb_substr($subject ?: 'Permintaan bantuan IT', 0, 119),
        ];
    }

    public static function portalTitle(array $fields): string
    {
        return $fields['name'] . ' - ' . mb_substr(str_replace(' - ', ' – ', $fields['site']), 0, 65) . ' - ' . $fields['summary'];
    }

    public static function locationId(string $site, int $entity): int
    {
        global $DB;
        $rows = $DB->request([
            'SELECT' => ['id'], 'FROM' => 'glpi_locations',
            'WHERE' => ['name' => $site] + getEntitiesRestrictCriteria('glpi_locations', '', $entity, true),
            'LIMIT' => 2,
        ]);
        return count($rows) === 1 ? (int) $rows->current()['id'] : 0;
    }

    public static function describe(array $fields): ?array
    {
        $content = self::plain((string) $fields['content']);
        $title = (string) $fields['name'];
        if (preg_match('/^\[HELPDESK_ZABBIX_V1:([^\]]+)\]/', $content, $match)) {
            return ['source' => 'zabbix', 'host' => rawurldecode($match[1]), 'summary' => $title];
        }
        if (!preg_match('/^\[HELPDESK_(WHATSAPP|PORTAL)_V1\]/', $content, $match)) {
            return null;
        }
        $parts = explode(' - ', $title, 3);
        if (count($parts) !== 3) {
            return ['source' => strtolower($match[1]), 'summary' => $title];
        }
        return ['source' => strtolower($match[1]), 'name' => $parts[0], 'site' => $parts[1], 'summary' => $parts[2]];
    }

    public static function cell(string $link, string $title, ?array $details): string
    {
        if (isset($details['host'])) {
            return $link . ' · <strong>' . htmlescape($details['host']) . '</strong><br>' . htmlescape($details['summary']);
        }
        if (isset($details['site'])) {
            return $link . '<br>' . htmlescape($details['name']) . ' - <strong>' . htmlescape($details['site'])
                . '</strong> - ' . htmlescape($details['summary']);
        }
        return $link . '<br>' . htmlescape($title);
    }
}
