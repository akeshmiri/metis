{{/*
Métis component Deployment template
*/}}
{{- define "metis.deployment" }}
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ printf "%s-%s" .Release.Name .name | trunc 63 | trimSuffix "-" }}
  labels:
    {{- include "metis.labels" . | nindent 4 }}
spec:
  replicas: {{ .replicas | default .defaultValues.replicas }}
  revisionHistoryLimit: {{ .revisionHistoryLimit | default .defaultValues.revisionHistoryLimit }}
  selector:
    matchLabels:
      {{- include "metis.selectorLabels" . | nindent 6 }}
  template:
    metadata:
      labels:
        {{- include "metis.selectorLabels" . | nindent 8 }}
        {{- include "metis.workloadLabels" . | nindent 8 }}
    spec:
      {{- if or .defaultValues.image.pullSecrets ((.imageOverride).pullSecrets) }}
      imagePullSecrets:
        {{- ((.imageOverride).pullSecrets) | default .defaultValues.image.pullSecrets | toYaml | nindent 8 }}
      {{- end }}
      serviceAccountName: {{ include "metis.serviceAccountName" . }}
      {{- $schedulingRules := .schedulingRules | default dict }}
      {{- if or .defaultValues.schedulingRules.nodeSelector $schedulingRules.nodeSelector }}
      nodeSelector:
        {{- $schedulingRules.nodeSelector | default .defaultValues.schedulingRules.nodeSelector | toYaml | nindent 8 }}
      {{- end }}
      containers:
        - name: {{ .name }}
          image: {{ printf "%s/%s/%s:%s" (((.imageOverride).registry) | default .defaultValues.image.registry) (((.imageOverride).repository) | default .defaultValues.image.repository) (((.imageOverride).name) | default .defaultValues.image.name) (((.imageOverride).tag) | default .defaultValues.image.tag) | quote }}
          imagePullPolicy: {{ ((.imageOverride).pullPolicy) | default .defaultValues.image.pullPolicy }}
          {{- if .defaultValues.securityContext }}
          {{/* Real bug found deploying this to a real cluster: readOnlyRootFilesystem
               is a CONTAINER-level securityContext field, not a Pod-level one --
               Kubernetes rejects "field not declared in schema" if it's placed under
               spec.template.spec.securityContext (where this used to be). runAsNonRoot
               is valid at both levels; applying the whole block at container level
               (where every field in it IS valid) is the fix. */}}
          securityContext:
            {{- .defaultValues.securityContext | toYaml | nindent 12 }}
          {{- end }}
          {{- if or .ports }}
          ports:
            {{- include "metis.pod.ports" . | nindent 12 }}
          {{- end }}
          envFrom:
            - secretRef:
                name: {{ printf "%s-secrets" .Release.Name | trunc 63 | trimSuffix "-" }}
          env:
            {{- include "metis.pod.env" . | nindent 12 }}
          resources:
            {{- .resources | toYaml | nindent 12 }}
          {{- if .livenessProbe }}
          livenessProbe:
            {{- .livenessProbe | toYaml | nindent 12 }}
          {{- end }}
          {{- if .mountedConfigMaps }}
          volumeMounts:
          {{- range .mountedConfigMaps }}
            - name: {{ .name | lower }}
              mountPath: {{ .mountPath }}
              {{- if .subPath }}
              subPath: {{ .subPath }}
              {{- end }}
          {{- end }}
          {{- end }}
      {{- if .mountedConfigMaps }}
      volumes:
      {{- range .mountedConfigMaps }}
        - name: {{ .name | lower }}
          configMap:
            name: {{ printf "%s-%s" $.Release.Name .name | trunc 63 | trimSuffix "-" }}
      {{- end }}
      {{- end }}
{{- end }}

{{/*
Métis component Service template
*/}}
{{- define "metis.service" }}
{{- if .ports }}
---
apiVersion: v1
kind: Service
metadata:
  name: {{ printf "%s-%s" .Release.Name .name | trunc 63 | trimSuffix "-" }}
  labels:
    {{- include "metis.labels" . | nindent 4 }}
spec:
  selector:
    {{- include "metis.selectorLabels" . | nindent 4 }}
  ports:
    {{- range .ports }}
    - name: {{ .name }}
      port: {{ .value }}
      targetPort: {{ .value }}
    {{- end }}
{{- end }}
{{- end }}

{{/*
Métis component CronJob template (guardrail-corpus-runner uses this instead
of Deployment -- it's a scheduled task, not a long-running service)
*/}}
{{- define "metis.cronjob" }}
---
apiVersion: batch/v1
kind: CronJob
metadata:
  name: {{ printf "%s-%s" .Release.Name .name | trunc 63 | trimSuffix "-" }}
  labels:
    {{- include "metis.labels" . | nindent 4 }}
spec:
  schedule: {{ .schedule | quote }}
  jobTemplate:
    spec:
      template:
        metadata:
          labels:
            {{- include "metis.selectorLabels" . | nindent 12 }}
            {{- include "metis.workloadLabels" . | nindent 12 }}
        spec:
          serviceAccountName: {{ include "metis.serviceAccountName" . }}
          restartPolicy: OnFailure
          containers:
            - name: {{ .name }}
              image: {{ printf "%s/%s/%s:%s" (((.imageOverride).registry) | default .defaultValues.image.registry) (((.imageOverride).repository) | default .defaultValues.image.repository) (((.imageOverride).name) | default .defaultValues.image.name) (((.imageOverride).tag) | default .defaultValues.image.tag) | quote }}
              imagePullPolicy: {{ ((.imageOverride).pullPolicy) | default .defaultValues.image.pullPolicy }}
              envFrom:
                - secretRef:
                    name: {{ printf "%s-secrets" .Release.Name | trunc 63 | trimSuffix "-" }}
              env:
                {{- include "metis.pod.env" . | nindent 16 }}
              resources:
                {{- .resources | toYaml | nindent 16 }}
              {{- if .mountedConfigMaps }}
              volumeMounts:
              {{- range .mountedConfigMaps }}
                - name: {{ .name | lower }}
                  mountPath: {{ .mountPath }}
                  {{- if .subPath }}
                  subPath: {{ .subPath }}
                  {{- end }}
              {{- end }}
              {{- end }}
          {{- if .mountedConfigMaps }}
          volumes:
          {{- range .mountedConfigMaps }}
            - name: {{ .name | lower }}
              configMap:
                name: {{ printf "%s-%s" $.Release.Name .name | trunc 63 | trimSuffix "-" }}
          {{- end }}
          {{- end }}
{{- end }}
