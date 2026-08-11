<script setup lang="ts">
// SeedResult: 种子完成/失败结果覆盖层
// 依据: 迭代/v3/README.md Phase 3 §SeedResult
import { useRouter } from '#imports'
import ActionButton from '@antfu/design/components/Action/ActionButton.vue'

interface FailedEtf {
  code: string
  name?: string
  error?: string
}

interface Props {
  status: 'ready' | 'error'
  totalCount: number
  successCount?: number
  failedEtfs?: FailedEtf[]
  errorMessage?: string
}

withDefaults(defineProps<Props>(), {
  successCount: 0,
  failedEtfs: () => [],
  errorMessage: '',
})

const emit = defineEmits<{
  retry: [mode: 'full' | 'failed_only']
  enter: []
}>()

const router = useRouter()

function onEnter() {
  emit('enter')
  router.push('/dashboard')
}
</script>

<template>
  <div class="flex flex-col items-center gap-4 text-center">
    <!-- 成功 -->
    <template v-if="status === 'ready'">
      <span class="i-ph-check-circle-duotone text-6xl color-primary-400" />
      <h2 class="text-lg font-medium color-base">
        {{ successCount }}/{{ totalCount }} 只 ETF 数据就绪
      </h2>
      <p v-if="failedEtfs.length > 0" class="text-xs op-fade max-w-md">
        以下 ETF 数据获取失败：{{ failedEtfs.map(f => f.code).join('、') }}
      </p>
      <div class="flex gap-2 mt-2">
        <ActionButton variant="primary" @click="onEnter">
          <span class="i-ph-arrow-right-duotone" />进入系统
        </ActionButton>
        <ActionButton
          v-if="failedEtfs.length > 0"
          variant="action"
          @click="emit('retry', 'failed_only')"
        >
          <span class="i-ph-arrow-clockwise-duotone" />仅重试失败的
        </ActionButton>
      </div>
    </template>

    <!-- 失败 -->
    <template v-else>
      <span class="i-ph-x-circle-duotone text-6xl color-down" />
      <h2 class="text-lg font-medium color-base">数据初始化失败</h2>
      <p class="text-xs op-fade max-w-md">
        {{ errorMessage || 'AkShare 不可用，请检查网络连接后重试' }}
      </p>
      <ActionButton variant="primary" class="mt-2" @click="emit('retry', 'full')">
        <span class="i-ph-arrow-clockwise-duotone" />全部重试
      </ActionButton>
    </template>
  </div>
</template>
