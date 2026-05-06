<template>
  <div class="rag-documents">
    <div class="toolbar">
      <h3>知识库文档</h3>
      <div>
        <input
          ref="fileInput"
          type="file"
          multiple
          accept=".pdf,.docx,.doc,.xlsx,.xls,.txt,.md,.csv"
          style="display: none"
          @change="onFilesPicked"
        />
        <ElButton type="primary" @click="($refs.fileInput as HTMLInputElement).click()">
          <i class="iconfont-sys">&#xe61b;</i> 上传文档
        </ElButton>
      </div>
    </div>

    <div v-if="pendingFiles.length > 0" class="upload-queue">
      <div v-for="(f, i) in pendingFiles" :key="i" class="queue-item">
        <span>{{ f.name }}</span>
        <span class="file-size">{{ formatSize(f.size) }}</span>
      </div>

      <div style="margin-top: 8px">
        <ElButton type="success" size="small" @click="doUpload" :loading="uploading">
          确认上传 ({{ pendingFiles.length }} 个文件)
        </ElButton>
        <ElButton size="small" :disabled="uploading" @click="pendingFiles = []">取消</ElButton>
      </div>

      <div v-if="uploading" class="upload-progress">
        <div class="progress-header">
          <span>上传进度</span>
          <span>{{ uploadProgress }}%</span>
        </div>
        <ElProgress :percentage="uploadProgress" :stroke-width="10" />
        <div class="progress-stage">{{ uploadStage }}</div>
      </div>

      <div v-if="uploadResult" class="upload-result">
        <div class="result-summary" :class="{ fail: uploadResult.failed > 0 }">
          {{ uploadResult.message }}
        </div>
        <div
          v-for="(r, i) in uploadResult.results"
          :key="i"
          :class="['result-item', r.success ? 'ok' : 'fail']"
        >
          <span class="result-file">{{ r.filename }}</span>
          <span class="result-message">{{ r.success ? '成功' : '失败' }}：{{ r.message }}</span>
        </div>
      </div>
    </div>

    <ElTable
      :data="documents"
      v-loading="loading"
      style="margin-top: 16px"
      empty-text="暂无文档，请上传 PDF、Word、Excel、Markdown 或 CSV"
    >
      <ElTableColumn prop="filename" label="文件名" min-width="200" />
      <ElTableColumn prop="file_type" label="类型" width="90" />
      <ElTableColumn prop="chunk_count" label="分块数" width="90" />
      <ElTableColumn label="操作" width="100" fixed="right">
        <template #default="{ row }">
          <ElButton type="danger" size="small" text @click="handleDelete(row.filename)">
            删除
          </ElButton>
        </template>
      </ElTableColumn>
    </ElTable>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { batchUploadRagDocuments, deleteRagDocument, fetchRagDocuments } from '@/api/rag'

defineOptions({ name: 'RagDocuments' })

const documents = ref<any[]>([])
const loading = ref(false)
const pendingFiles = ref<File[]>([])
const uploading = ref(false)
const uploadResult = ref<any>(null)
const uploadProgress = ref(0)
const uploadStage = ref('')
const fileInput = ref<HTMLInputElement>()

let progressTimer: ReturnType<typeof setInterval> | null = null

function formatSize(bytes: number): string {
  if (!bytes) return '-'
  const units = ['B', 'KB', 'MB', 'GB']
  let i = 0
  let size = bytes
  while (size >= 1024 && i < units.length - 1) {
    size /= 1024
    i++
  }
  return `${size.toFixed(1)} ${units[i]}`
}

function stopProgressTimer() {
  if (progressTimer) {
    clearInterval(progressTimer)
    progressTimer = null
  }
}

function startProgressSimulation() {
  stopProgressTimer()
  uploadProgress.value = 5
  uploadStage.value = '正在上传文件...'

  progressTimer = setInterval(() => {
    if (uploadProgress.value < 35) {
      uploadProgress.value += 5
      uploadStage.value = '正在上传文件...'
    } else if (uploadProgress.value < 85) {
      uploadProgress.value += 3
      uploadStage.value = '正在解析文档并生成向量...'
    }
  }, 500)
}

async function loadDocuments() {
  loading.value = true
  try {
    const res = await fetchRagDocuments()
    documents.value = (res as any).documents || []
  } catch {
    /* ignore */
  } finally {
    loading.value = false
  }
}

function onFilesPicked(e: Event) {
  const input = e.target as HTMLInputElement
  if (input.files) pendingFiles.value = Array.from(input.files)
  uploadResult.value = null
  input.value = ''
}

async function doUpload() {
  if (pendingFiles.value.length === 0) return

  uploading.value = true
  uploadResult.value = null
  startProgressSimulation()

  try {
    const res = await batchUploadRagDocuments(pendingFiles.value)
    uploadResult.value = res
    pendingFiles.value = []

    stopProgressTimer()
    uploadProgress.value = 92
    uploadStage.value = '正在刷新文档列表...'
    await loadDocuments()
    uploadProgress.value = 100
    uploadStage.value = '上传完成'

    const ok = (res as any).succeeded || 0
    const fail = (res as any).failed || 0
    const firstFail = ((res as any).results || []).find((item: any) => !item.success)

    if (fail > 0 && ok > 0) {
      ElMessage.warning(
        `上传完成：${ok} 成功，${fail} 失败。${firstFail ? `首个失败原因：${firstFail.message}` : ''}`
      )
    } else if (fail > 0) {
      ElMessage.error(`上传失败：${firstFail?.message || '请查看下方失败原因'}`)
    } else {
      ElMessage.success(`上传完成：${ok} 成功，${fail} 失败`)
    }
  } catch (e: any) {
    stopProgressTimer()
    uploadProgress.value = 100
    uploadStage.value = '上传失败'
    ElMessage.error(e.message || '上传失败，请稍后重试')
  } finally {
    uploading.value = false
    setTimeout(() => {
      if (!uploading.value) {
        uploadProgress.value = 0
        uploadStage.value = ''
      }
    }, 1200)
  }
}

async function handleDelete(filename: string) {
  try {
    await ElMessageBox.confirm(`确定删除 "${filename}" 吗？`, '确认', { type: 'warning' })
    await deleteRagDocument(filename)
    ElMessage.success('删除成功')
    await loadDocuments()
  } catch {
    /* cancel */
  }
}

onMounted(loadDocuments)
</script>

<style lang="scss" scoped>
.rag-documents {
  padding: 20px;
}

.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;

  h3 {
    margin: 0;
  }
}

.upload-queue {
  margin-top: 12px;
  padding: 16px;
  background: var(--el-fill-color-light);
  border-radius: 8px;

  .queue-item {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 4px 0;

    .file-size {
      color: var(--el-text-color-secondary);
      font-size: 12px;
    }
  }
}

.upload-progress {
  margin-top: 14px;
  padding: 12px;
  background: var(--el-bg-color);
  border-radius: 6px;

  .progress-header {
    display: flex;
    justify-content: space-between;
    margin-bottom: 8px;
    font-size: 13px;
    font-weight: 600;
  }

  .progress-stage {
    margin-top: 8px;
    color: var(--el-text-color-secondary);
    font-size: 12px;
  }
}

.upload-result {
  margin-top: 12px;
  padding: 12px;
  background: var(--el-bg-color);
  border-radius: 6px;

  .result-summary {
    font-weight: 600;
    margin-bottom: 8px;

    &.fail {
      color: var(--el-color-danger);
    }
  }

  .result-item {
    display: flex;
    justify-content: space-between;
    gap: 12px;
    padding: 4px 0;
    font-size: 13px;

    &.fail {
      color: var(--el-color-danger);
    }

    &.ok {
      color: var(--el-color-success);
    }
  }

  .result-file {
    flex-shrink: 0;
  }

  .result-message {
    flex: 1;
    text-align: right;
    word-break: break-word;
  }
}
</style>
