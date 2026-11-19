<?php

require_once __DIR__ . '/ticketformat.class.php';

class PluginLayananitTicketFeed
{
    public static function baseline(): int
    {
        global $DB;
        $result = $DB->request(['SELECT' => ['id'], 'FROM' => 'glpi_tickets', 'ORDER' => 'id DESC', 'LIMIT' => 1]);
        return (int) ($result->current()['id'] ?? 0);
    }

    public static function page(int $after, ?int $through): array
    {
        global $DB;
        $through ??= self::baseline();
        $through = max($after, $through);
        $query = $DB->request([
            'SELECT' => ['id'],
            'FROM' => 'glpi_tickets',
            'WHERE' => ['AND' => [['id' => ['>', $after]], ['id' => ['<=', $through]]]],
            'ORDER' => 'id ASC',
            'LIMIT' => 101,
        ]);
        $ids = array_map('intval', array_column(iterator_to_array($query, false), 'id'));
        $more = count($ids) > 100;
        $ids = array_slice($ids, 0, 100);
        return [
            'tickets' => array_values(self::visible($ids)),
            'after' => $more ? end($ids) : $through,
            'through' => $through,
            'more' => $more,
        ];
    }

    public static function visible(array $ids): array
    {
        $visible = [];
        $ticket = new Ticket();
        foreach ($ids as $id) {
            if (!$ticket->can($id, READ) || !empty($ticket->fields['is_deleted'])) {
                continue;
            }
            $details = PluginLayananitTicketFormat::describe($ticket->fields);
            if ($details) {
                $visible[$id] = $details + ['id' => $id, 'title' => $ticket->fields['name']];
            }
        }
        return $visible;
    }
}
