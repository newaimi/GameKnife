import type { ManualEditSource, ManualEditTransferRecord } from "../../types/manualEdit";

const MANUAL_EDIT_TRANSFER_DB_NAME = "gameknife-manual-edit";
const MANUAL_EDIT_TRANSFER_STORE = "transfers";
const MANUAL_EDIT_TRANSFER_TTL_MS = 30 * 60 * 1000;
const MANUAL_EDIT_TRANSFER_MAX_RECORDS = 6;

export async function saveManualEditTransfer(source: Pick<ManualEditSource, "name" | "url" | "sourceFileId" | "sourceContext">) {
  const response = await fetch(source.url);
  if (!response.ok) throw new Error("Could not read image.");
  const blob = await response.blob();
  const database = await openManualEditTransferDatabase();
  try {
    await cleanupManualEditTransfers(database, Date.now(), MANUAL_EDIT_TRANSFER_MAX_RECORDS - 1);
    const id = crypto.randomUUID();
    const record: ManualEditTransferRecord = {
      id,
      name: source.name || "Manual edit image",
      blob,
      sourceFileId: source.sourceFileId,
      sourceContext: source.sourceContext,
      createdAt: Date.now(),
    };

    // Processed images can be several megabytes and do not belong in a URL or localStorage. IndexedDB keeps
    // the Blob available to a same-origin tab, and stale records are removed before each write.
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
    request.onerror = () => reject(request.error ?? new Error("Could not open the local image cache."));
  });
}

function writeManualEditTransfer(database: IDBDatabase, record: ManualEditTransferRecord) {
  return new Promise<void>((resolve, reject) => {
    const transaction = database.transaction(MANUAL_EDIT_TRANSFER_STORE, "readwrite");
    const store = transaction.objectStore(MANUAL_EDIT_TRANSFER_STORE);
    store.put(record);
    transaction.oncomplete = () => resolve();
    transaction.onerror = () => reject(transaction.error ?? new Error("Could not write the image to the local cache."));
  });
}

function consumeManualEditTransfer(database: IDBDatabase, id: string) {
  return new Promise<ManualEditTransferRecord | null>((resolve, reject) => {
    const transaction = database.transaction(MANUAL_EDIT_TRANSFER_STORE, "readwrite");
    const store = transaction.objectStore(MANUAL_EDIT_TRANSFER_STORE);
    let transferRecord: ManualEditTransferRecord | null = null;
    const request = store.get(id);
    request.onerror = () => reject(request.error ?? new Error("Could not read the image from the local cache."));
    request.onsuccess = () => {
      transferRecord = (request.result as ManualEditTransferRecord | undefined) ?? null;
      if (transferRecord) {
        // A transfer record exists for one handoff from result preview to a new tab. Delete it after the Blob is
        // consumed so repeated large-image edits do not accumulate temporary copies.
        store.delete(id);
      }
    };
    transaction.oncomplete = () => resolve(transferRecord);
    transaction.onerror = () => reject(transaction.error ?? new Error("Could not read the image from the local cache."));
  });
}

function cleanupManualEditTransfers(database: IDBDatabase, now: number, maxRecords: number) {
  return new Promise<void>((resolve, reject) => {
    const transaction = database.transaction(MANUAL_EDIT_TRANSFER_STORE, "readwrite");
    const store = transaction.objectStore(MANUAL_EDIT_TRANSFER_STORE);
    const request = store.getAll();
    request.onerror = () => reject(request.error ?? new Error("Could not clean the image cache."));
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
    transaction.onerror = () => reject(transaction.error ?? new Error("Could not clean the image cache."));
  });
}
