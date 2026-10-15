<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'

const props = defineProps<{ open: boolean }>()

const emit = defineEmits<{ (e: 'close'): void }>()

const dialogRef = ref<HTMLDialogElement | null>(null)

watch(
  () => props.open,
  async (open) => {
    await nextTick()
    const dialog = dialogRef.value
    if (!dialog) return
    if (open && !dialog.open) dialog.showModal()
    if (!open && dialog.open) dialog.close()
  },
)

function onClose() {
  emit('close')
}
</script>

<template>
  <dialog ref="dialogRef" class="dialog" @close="onClose" @cancel="onClose">
    <slot />
  </dialog>
</template>
