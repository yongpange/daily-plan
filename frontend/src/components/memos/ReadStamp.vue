<script setup lang="ts">
// 点阅打卡印章动画 —— 平移 web-legacy/app.js playReadStamp 生成的 DOM 与
// styles.css L2627-2865 的 read-stamp-* 动画（动画名保持原样，配合 scoped 作用域）
defineProps<{
  count: number
  caption: string
  milestone: boolean
}>()
</script>

<template>
  <div class="read-stamp-pop" :class="{ 'is-milestone': milestone }" role="status">
    <span class="read-stamp-ring"></span>
    <span class="read-stamp-ink">
      <strong>已阅</strong>
      <em>{{ count }}</em>
    </span>
    <span class="read-stamp-caption">{{ caption }}</span>
    <span class="read-stamp-speck"></span>
    <span class="read-stamp-speck"></span>
    <span class="read-stamp-speck"></span>
    <span class="read-stamp-speck"></span>
  </div>
</template>

<style scoped>
.read-stamp-pop {
  position: absolute;
  inset: 0;
  z-index: 3;
  pointer-events: none;
  animation: read-stamp-fade 1400ms ease forwards;
}

.read-stamp-ink {
  position: absolute;
  top: 50%;
  left: 50%;
  display: grid;
  width: 86px;
  height: 86px;
  margin-top: -43px;
  margin-left: -43px;
  place-items: center;
  align-content: center;
  border: 3px solid #c4493a;
  border-radius: 50%;
  color: #c23b32;
  background:
    radial-gradient(circle at 32% 28%, rgba(255, 255, 255, 0.45), transparent 42%),
    rgba(196, 73, 58, 0.08);
  box-shadow:
    inset 0 0 0 1px rgba(194, 59, 50, 0.35),
    0 10px 18px rgba(194, 59, 50, 0.12);
  animation: read-stamp-slam 780ms cubic-bezier(0.16, 0.84, 0.32, 1.15) both;
}

.read-stamp-ink strong {
  font-size: 18px;
  font-weight: 800;
  letter-spacing: 0.18em;
  line-height: 1;
}

.read-stamp-ink em {
  margin-top: 3px;
  font-style: normal;
  font-size: 13px;
  font-variant-numeric: tabular-nums;
  font-weight: 750;
}

.read-stamp-pop.is-milestone .read-stamp-ink {
  width: 98px;
  height: 98px;
  margin-top: -49px;
  margin-left: -49px;
  box-shadow:
    inset 0 0 0 1px rgba(194, 59, 50, 0.4),
    inset 0 0 0 6px rgba(194, 59, 50, 0.08),
    0 14px 24px rgba(194, 59, 50, 0.18);
}

.read-stamp-ring {
  position: absolute;
  top: 50%;
  left: 50%;
  width: 92px;
  height: 92px;
  margin-top: -46px;
  margin-left: -46px;
  border: 2px solid rgba(194, 59, 50, 0.42);
  border-radius: 50%;
  animation: read-stamp-ring 700ms ease-out 160ms both;
}

.read-stamp-caption {
  position: absolute;
  top: 50%;
  right: calc(50% + 64px);
  margin-top: -13px;
  padding: 3px 10px;
  border-radius: 999px;
  color: #9d322b;
  background: rgba(255, 247, 244, 0.94);
  font-size: 12px;
  font-weight: 750;
  letter-spacing: 0.04em;
  white-space: nowrap;
  animation: read-caption-rise 1100ms ease both;
}

.read-stamp-speck {
  position: absolute;
  top: 50%;
  left: 50%;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #c23b32;
  opacity: 0;
  animation: read-speck-fly 700ms ease-out 150ms both;
}

.read-stamp-speck:nth-child(4) {
  --dx: -62px;
  --dy: -18px;
}

.read-stamp-speck:nth-child(5) {
  --dx: 58px;
  --dy: -28px;
  width: 4px;
  height: 4px;
}

.read-stamp-speck:nth-child(6) {
  --dx: -40px;
  --dy: 34px;
  width: 5px;
  height: 5px;
}

.read-stamp-speck:nth-child(7) {
  --dx: 48px;
  --dy: 22px;
}

@keyframes read-stamp-slam {
  0% {
    transform: translateY(-16px) rotate(-28deg) scale(1.55);
    opacity: 0;
  }

  42% {
    transform: translateY(2px) rotate(-8deg) scale(0.9);
    opacity: 1;
  }

  62% {
    transform: translateY(0) rotate(-16deg) scale(1.06);
  }

  100% {
    transform: rotate(-12deg) scale(1);
    opacity: 1;
  }
}

@keyframes read-stamp-ring {
  0% {
    transform: scale(0.72);
    opacity: 0.7;
  }

  100% {
    transform: scale(1.85);
    opacity: 0;
  }
}

@keyframes read-caption-rise {
  0% {
    transform: translateY(8px);
    opacity: 0;
  }

  28% {
    transform: translateY(0);
    opacity: 1;
  }

  78% {
    opacity: 1;
  }

  100% {
    transform: translateY(-6px);
    opacity: 0;
  }
}

@keyframes read-stamp-fade {
  0%,
  72% {
    opacity: 1;
  }

  100% {
    opacity: 0;
  }
}

@keyframes read-speck-fly {
  0% {
    transform: translate(-50%, -50%) scale(0.4);
    opacity: 0;
  }

  30% {
    opacity: 0.85;
  }

  100% {
    transform: translate(calc(-50% + var(--dx)), calc(-50% + var(--dy))) scale(0.7);
    opacity: 0;
  }
}

@media (prefers-reduced-motion: reduce) {
  .read-stamp-pop,
  .read-stamp-ink,
  .read-stamp-ring,
  .read-stamp-caption,
  .read-stamp-speck {
    animation: none;
  }
}
</style>
