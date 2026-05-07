<template>
  <div class="flex h-screen flex-col items-center justify-center gap-4 p-6 text-center">
    <h1 class="text-xl font-semibold">Sprih Reporting Agent</h1>
    <p class="text-sm text-gray-500">
      Phase 1 scaffold. Backend integration arrives in Phase 2.
    </p>
    <p class="text-xs text-gray-400">
      Office host: {{ host }}
    </p>
  </div>
</template>

<script lang="ts" setup>
import { ref } from 'vue'

const host = ref<string>('detecting…')

if (typeof Office !== 'undefined' && Office.context) {
  host.value = Office.context.host?.toString() ?? 'unknown'
}
</script>
