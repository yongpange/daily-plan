<script setup lang="ts">
import { useUiStore } from '../../stores/ui'

const ui = useUiStore()
</script>

<template>
  <div v-show="ui.toastVisible" class="toast" :class="{ 'is-error': ui.toastIsError }" role="status">
    {{ ui.toastMessage }}
  </div>
</template>
