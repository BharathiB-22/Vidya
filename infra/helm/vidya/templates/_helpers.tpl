{{/*
Expand the chart name.
*/}}
{{- define "vidya.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a fully-qualified name for a release. Truncated at 63 chars (DNS limit).
*/}}
{{- define "vidya.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create the chart label string (name-version, + replaced with _).
*/}}
{{- define "vidya.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels applied to every resource.
*/}}
{{- define "vidya.labels" -}}
helm.sh/chart: {{ include "vidya.chart" . }}
{{ include "vidya.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels — stable subset used in matchLabels (must not change after install).
*/}}
{{- define "vidya.selectorLabels" -}}
app.kubernetes.io/name: {{ include "vidya.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Component-specific fully-qualified name.
Usage: {{ include "vidya.componentName" (list . "api") }}
*/}}
{{- define "vidya.componentName" -}}
{{- $ctx := index . 0 -}}
{{- $component := index . 1 -}}
{{- printf "%s-%s" (include "vidya.fullname" $ctx) $component | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Component selector labels — used in Deployment.spec.selector.matchLabels and
Pod template metadata. Stable: do not add fields that may change.
Usage: {{ include "vidya.componentSelectorLabels" (list . "api") }}
*/}}
{{- define "vidya.componentSelectorLabels" -}}
{{- $ctx := index . 0 -}}
{{- $component := index . 1 -}}
app.kubernetes.io/name: {{ include "vidya.name" $ctx }}
app.kubernetes.io/instance: {{ $ctx.Release.Name }}
app.kubernetes.io/component: {{ $component }}
{{- end }}

{{/*
Component common labels (selector labels + chart/version/managed-by).
Usage: {{ include "vidya.componentLabels" (list . "api") }}
*/}}
{{- define "vidya.componentLabels" -}}
{{- $ctx := index . 0 -}}
{{- $component := index . 1 -}}
helm.sh/chart: {{ include "vidya.chart" $ctx }}
{{ include "vidya.componentSelectorLabels" (list $ctx $component) }}
{{- if $ctx.Chart.AppVersion }}
app.kubernetes.io/version: {{ $ctx.Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ $ctx.Release.Service }}
{{- end }}

{{/*
ServiceAccount name.
*/}}
{{- define "vidya.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "vidya.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Image reference for a component, respecting the global registry prefix.
Usage: {{ include "vidya.image" (list . .Values.api.image) }}
*/}}
{{- define "vidya.image" -}}
{{- $ctx := index . 0 -}}
{{- $img := index . 1 -}}
{{- $registry := $ctx.Values.global.imageRegistry -}}
{{- if $registry }}
{{- printf "%s/%s:%s" $registry $img.repository $img.tag }}
{{- else }}
{{- printf "%s:%s" $img.repository $img.tag }}
{{- end }}
{{- end }}

{{/*
Standard environment variable block — shared by api, worker, workerHeavy, migrate.
Mounts non-secret env from ConfigMap and secret env from Secret (or ExternalSecret).
*/}}
{{- define "vidya.commonEnvFrom" -}}
- configMapRef:
    name: {{ include "vidya.fullname" . }}-config
- secretRef:
    name: {{ include "vidya.fullname" . }}-secret
{{- end }}

{{/*
Node selector block for a component values map.
Usage: {{ include "vidya.nodeSelector" .Values.api.nodeSelector }}
*/}}
{{- define "vidya.nodeSelector" -}}
{{- with . }}
nodeSelector:
  {{- toYaml . | nindent 2 }}
{{- end }}
{{- end }}

{{/*
Tolerations block for a component values map.
Usage: {{ include "vidya.tolerations" .Values.api.tolerations }}
*/}}
{{- define "vidya.tolerations" -}}
{{- with . }}
tolerations:
  {{- toYaml . | nindent 2 }}
{{- end }}
{{- end }}

{{/*
Image pull secrets block.
*/}}
{{- define "vidya.imagePullSecrets" -}}
{{- with .Values.global.imagePullSecrets }}
imagePullSecrets:
  {{- toYaml . | nindent 2 }}
{{- end }}
{{- end }}
