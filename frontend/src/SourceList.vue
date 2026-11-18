<script setup>
defineProps({ rows: { type: Array, required: true } })
</script>

<template>
  <details v-for="row in rows" :key="row.id || row.source">
    <summary>{{ row.id }} · {{ row.source }}</summary>
    <pre>{{ row.text }}</pre>
  </details>
</template>
