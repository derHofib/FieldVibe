# Begriffsverzeichnis (UI-Vokabular)

Ein Begriff pro Sache -- in Beschriftungen, Seitentiteln, Buttons und
Fehlermeldungen. Bezeichner im Code und URLs bleiben unverändert
(`/feed`, `vorgaenge`, `geschaeft` usw.), umbenannt wird nur, was Nutzer sehen.

| Begriff in der UI | Bedeutung | Nicht verwenden / Hinweis |
|---|---|---|
| Vorgang / Vorgänge | Das Ticket/der Einsatz (Titel, Status, Chat, Zeit). Tab "Vorgänge", Buttons "Neuer Vorgang", "Vorgang übernehmen", "Folge-Vorgang" | "Ticket", "Feed" als Tab-Name, "Aufträge" für Vorgänge |
| Auftrag / Aufträge | Nur die separate Entität Auftrag (Office `/auftraege`) | nicht für Vorgänge |
| Dauerauftrag / Dauer-Aufträge | Wiederkehrender Auftrag, der Vorgänge erzeugt | bleibt, ist ein eigener Begriff |
| Arbeitszeit | Erfasste Zeiten (Seite `/statistik`, Menüpunkt, CSV-Export) | "Zeiterfassung" in sichtbaren Texten |
| Kunden, Material, Rechnungen | Eigene Seiten (`GeschaeftPage` entfällt, BACKLOG 7 damit erledigt) | "Geschäft" |
| Anlage | Betriebsmittel beim Kunden | |
| Standort | Site eines Kunden | |
| Mandant | Tenant (Betrieb, der FieldVibe nutzt) | |
| Mangel | Defekt, der zu Angebot und Rechnung führt | |

Das Kundenportal spricht Endkunden an und nennt Vorgänge weiterhin
"Aufträge" (Kundensicht) -- bewusst nicht vereinheitlicht.
