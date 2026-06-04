import type { ManualEditSource, ManualEditTransferRecord } from "../../types/manualEdit";

const MANUAL_EDIT_TRANSFER_DB_NAME = "gameknife-manual-edit";
const MANUAL_EDIT_TRANSFER_STORE = "transfers";
const MANUAL_EDIT_TRANSFER_TTL_MS = 30 * 60 * 1000;
const MANUAL_EDIT_TRANSFER_MAX_RECORDS = 6;

export async function saveManualEditTransfer(source: Pick<ManualEditSource, "name" | "url" | "sourceFileId" | "sourceContext">) {
  const response = await fetch(source.url);
  if (!response.ok) throw new Error("图片读取失败。");
  const blob = await response.blob();
  const database = await openManualEditTransferDatabase();
  try {
    await cleanupManualEditTransfers(database, Date.now(), MANUAL_EDIT_TRANSFER_MAX_RECORDS - 1);
    const id = crypto.randomUUID();
    const record: ManualEditTransferRecord = {
      id,
      name: source.name || "手动编辑图片",
      blob,
      sourceFileId: source.sourceFileId,
      sourceContext: source.sourceContext,
      createdAt: Date.now(),
    };

    // 处理后的图片可能是几 MB 甚至更大，不能塞进 URL 或 localStorage。
    // IndexedDB 可以跨同源标签页保存 Blob，新开的手动编辑页才能稳定读到这份临时图片。
    // 写入前会先清理旧记录，避免连续打开大图时把浏览器本地配额撑满。
    await writeManualEditTransfer(database, record);
    return id;
  } finally {
    database.close();
  }
}

export async function loadManualEditTransfer(id: string): Promise<ManualEditSource | null> {
  const database = await openManualEditTransferDatabase();
  const record = await consumeManualEditTransfer(database, id).finally(() => database.close());
  if (!record) return null;

  return {
    name: record.name,
    url: URL.createObjectURL(record.blob),
    blob: record.blob,
    sourceFileId: record.sourceFileId,
    sourceContext: record.sourceContext,
    revokeObjectUrl: true,
  };
}

function openManualEditTransferDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(MANUAL_EDIT_TRANSFER_DB_NAME, 1);
    request.onupgradeneeded = () => {
      const database = request.result;
      if (!database.objectStoreNames.contains(MANUAL_EDIT_TRANSFER_STORE)) {
        database.createObjectStore(MANUAL_EDIT_TRANSFER_STORE, { keyPath: "id" });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error ?? new Error("本地图片缓存打开失败。"));
  });
}

function writeManualEditTransfer(database: IDBDatabase, record: ManualEditTransferRecord) {
  return new Promise<void>((resolve, reject) => {
    const transaction = database.transaction(MANUAL_EDIT_TRANSFER_STORE, "readwrite");
    const store = transaction.objectStore(MANUAL_EDIT_TRANSFER_STORE);
    store.put(record);
    transaction.oncomplete = () => resolve();
    transaction.onerror = () => reject(transaction.error ?? new Error("图片写入本地缓存失败。"));
  });
}

function consumeManualEditTransfer(database: IDBDatabase, id: string) {
  return new Promise<ManualEditTransferRecord | null>((resolve, reject) => {
    const transaction = database.transaction(MANUAL_EDIT_TRANSFER_STORE, "readwrite");
    const store = transaction.objectStore(MANUAL_EDIT_TRANSFER_STORE);
    let transferRecord: ManualEditTransferRecord | null = null;
    const request = store.get(id);
    request.onerror = () => reject(request.error ?? new Error("图片读取本地缓存失败。"));
    request.onsuccess = () => {
      transferRecord = (request.result as ManualEditTransferRecord | undefined) ?? null;
      if (transferRecord) {
        // 这个 IndexedDB 记录只用于“从结果预览交给新标签页”这一跳。
        // 新标签页拿到 Blob 后立即删除，可以防止用户连续编辑大图时留下大量临时副本。
        store.delete(id);
      }
    };
    transaction.oncomplete = () => resolve(transferRecord);
    transaction.onerror = () => reject(transaction.error ?? new Error("图片读取本地缓存失败。"));
  });
}

function cleanupManualEditTransfers(database: IDBDatabase, now: number, maxRecords: number) {
  return new Promise<void>((resolve, reject) => {
    const transaction = database.transaction(MANUAL_EDIT_TRANSFER_STORE, "readwrite");
    const store = transaction.objectStore(MANUAL_EDIT_TRANSFER_STORE);
    const request = store.getAll();
    request.onerror = () => reject(request.error ?? new Error("图片缓存清理失败。"));
    request.onsuccess = () => {
      const records = ((request.result as ManualEditTransferRecord[] | undefined) ?? []).sort((first, second) => second.createdAt - first.createdAt);
      const recordsToKeep = Math.max(0, maxRecords);
      records.forEach((record, index) => {
        if (now - record.createdAt > MANUAL_EDIT_TRANSFER_TTL_MS || index >= recordsToKeep) {
          store.delete(record.id);
        }
      });
    };
    transaction.oncomplete = () => resolve();
    transaction.onerror = () => reject(transaction.error ?? new Error("图片缓存清理失败。"));
  });
}

