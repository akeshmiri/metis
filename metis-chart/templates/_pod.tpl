{{/*
Get Pod Env — merges platform-wide defaults with component-level env, same
merge-by-name convention as the shared helper above.
*/}}
{{- define "metis.pod.env" -}}
{{- $allEnvs := list }}
{{- if .useDefault.env }}
{{-   $defaultEnvs := include "metis.envOverriden" (dict "env" .defaultValues.env "envOverrides" .defaultValues.envOverrides) | mustFromJson }}
{{-   range $defaultEnvs }}
{{-     $allEnvs = append $allEnvs . }}
{{-   end }}
{{- end }}
{{- if or .env .envOverrides }}
{{-   $localEnvs := include "metis.envOverriden" . | mustFromJson }}
{{-   range $localEnvs }}
{{-     $allEnvs = append $allEnvs . }}
{{-   end }}
{{- end }}
{{- tpl (toYaml $allEnvs) . }}
{{- end }}

{{/*
Get Pod ports
*/}}
{{- define "metis.pod.ports" -}}
{{- if .ports }}
{{-   range $port := .ports }}
- containerPort: {{ $port.value }}
  name: {{ $port.name }}
{{-   end }}
{{- end }}
{{- end }}
