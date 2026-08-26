{{/*
Expand the name of the chart.
*/}}
{{- define "metis.name" -}}
{{- default .Release.Name | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "metis.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "metis.labels" -}}
helm.sh/chart: {{ include "metis.chart" . }}
{{ include "metis.selectorLabels" . }}
{{ include "metis.workloadLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/part-of: metis
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Workload (Pod) labels
*/}}
{{- define "metis.workloadLabels" -}}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- if .name }}
app.kubernetes.io/component: {{ .name }}
app.kubernetes.io/name: {{ .name }}
{{- end }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "metis.selectorLabels" -}}
{{- if .name }}
app.kubernetes.io/name: {{ .name }}
{{- end }}
{{- end }}

{{/*
Merge default env vars with component-level overrides -- same override-by-name
semantics as a conventional orchestration chart (a component's own `env` entry with a matching
`name` wins over the platform-wide default, rather than duplicating it).
*/}}
{{- define "metis.envOverriden" -}}
{{- $mergedEnvs := list }}
{{- $envOverrides := default (list) .envOverrides }}
{{- range .env }}
{{-   $currentEnv := . }}
{{-   $hasOverride := false }}
{{-   range $envOverrides }}
{{-     if eq $currentEnv.name .name }}
{{-       $mergedEnvs = append $mergedEnvs . }}
{{-       $envOverrides = without $envOverrides . }}
{{-       $hasOverride = true }}
{{-     end }}
{{-   end }}
{{-   if not $hasOverride }}
{{-     $mergedEnvs = append $mergedEnvs $currentEnv }}
{{-   end }}
{{- end }}
{{- $mergedEnvs = concat $mergedEnvs $envOverrides }}
{{- mustToJson $mergedEnvs }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "metis.serviceAccountName" -}}
{{- if .serviceAccount.create }}
{{- default (include "metis.name" .) .serviceAccount.name }}
{{- else }}
{{- default "default" .serviceAccount.name }}
{{- end }}
{{- end }}
