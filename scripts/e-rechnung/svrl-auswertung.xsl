<?xml version="1.0" encoding="UTF-8"?>
<!-- Macht aus dem SVRL-Bericht der CEN-Regeln zeilenweise Text fuer pruefen.sh:
     "<FEHLER|WARNUNG> TAB <Regel-ID> TAB <Meldung> TAB <Fundstelle>". Eine leere Regelanwendung
     (kein CII-Wurzelelement) wird als eigener Fehler gemeldet, weil die Regeln dann
     stillschweigend nichts pruefen wuerden. -->
<xsl:stylesheet version="2.0"
    xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
    xmlns:svrl="http://purl.oclc.org/dsdl/svrl">
  <xsl:output method="text" encoding="UTF-8"/>

  <xsl:template match="/svrl:schematron-output">
    <xsl:if test="not(svrl:fired-rule)">
      <xsl:text>FEHLER&#9;KEINE-REGEL&#9;Keine Regel angewendet -- kein CII-Dokument (CrossIndustryInvoice)?&#9;/&#10;</xsl:text>
    </xsl:if>
    <xsl:for-each select="svrl:failed-assert | svrl:successful-report">
      <xsl:value-of select="if (@flag = ('warning', 'information')) then 'WARNUNG' else 'FEHLER'"/>
      <xsl:text>&#9;</xsl:text>
      <xsl:value-of select="@id"/>
      <xsl:text>&#9;</xsl:text>
      <xsl:value-of select="replace(normalize-space(svrl:text), '^\[[^\]]*\]-?\s*', '')"/>
      <xsl:text>&#9;</xsl:text>
      <xsl:value-of select="replace(@location, '\*:([A-Za-z]+)\[namespace-uri\(\)=''[^'']*''\]', '$1')"/>
      <xsl:text>&#10;</xsl:text>
    </xsl:for-each>
  </xsl:template>
</xsl:stylesheet>
