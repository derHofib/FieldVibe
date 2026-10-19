#!/usr/bin/env bash
# shellcheck disable=SC2034  # Variablen werden von den sourcenden Skripten benutzt
# Gepinnte Quellen und Pruefsummen der E-Rechnungs-Pruefwerkzeuge. Wird von
# installieren.sh und pruefen.sh gesourct; eine Aenderung hier ist eine bewusste
# Versionsanhebung (Pruefsummen dann neu bestimmen, siehe
# docs/konzepte/E_RECHNUNG_PRUEFUNG.md).

# Saxon-HE (XSLT-2.0-Prozessor) samt xmlresolver, beides von Maven Central.
SAXON_VERSION="12.9"
SAXON_SHA256="8f3a9216a537367132293eacbba9df062eace8f8b16a184af59e2e4839d4cd41"
XMLRESOLVER_VERSION="5.3.3"
XMLRESOLVER_SHA256="1fe4d5b92f708dcdb82dbce12919e0171e6b5ca62c6dca6220483625098feb5f"
XMLRESOLVER_DATA_SHA256="b0c487ad2f3e558be8d829c916d2458d10aca6a5bafa7a4d0524b70845e48a5c"

# Kompilierte CEN-Geschaeftsregeln (Schematron -> XSLT) fuer CII/EN 16931:
# Release validation-1.3.17 vom 2026-10-09 im Repo ConnectingEurope/eInvoicing-EN16931.
EN16931_REPO="https://github.com/ConnectingEurope/eInvoicing-EN16931.git"
EN16931_COMMIT="6e35e0ab8b09eb183f7d84b282e24ef95f9f5715"
EN16931_XSLT_PFAD="cii/xslt/EN16931-CII-validation.xslt"
EN16931_XSLT_SHA256="0757f07909938b1b297b8356ab7b66406c89f1b342325385d6a2def998c817f0"
