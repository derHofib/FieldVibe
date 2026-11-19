import type { StatusKey } from "../../components/apple/status";
import type { VorgangAnfrageStatus } from "../../types";

export const ANFRAGE_STATUS_PILLE: Record<VorgangAnfrageStatus, { ton: StatusKey; label: string }> = {
  offen: { ton: "neu", label: "Offen" },
  angenommen: { ton: "erledigt", label: "Angenommen" },
  abgelehnt: { ton: "geplant", label: "Abgelehnt" },
};
