export interface ConfirmCloseDialogProps {
  fileName: string;
  onSave: () => void;
  onDiscard: () => void;
  onCancel: () => void;
}

/** "Save / Don't Save / Cancel" prompt shown when closing a tab with unsaved edits. */
export function ConfirmCloseDialog({ fileName, onSave, onDiscard, onCancel }: ConfirmCloseDialogProps) {
  return (
    <div
      className="absolute inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
      onClick={onCancel}
    >
      <div
        className="w-[320px] rounded-lg border border-white/10 bg-[#161618] p-4 shadow-2xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="text-[13px] font-semibold text-[#e8e6e3]">是否保存更改？</div>
        <div className="mt-1.5 text-[12px] leading-5 text-[#9a9590]">
          文件 <span className="font-mono-code text-[#e8e6e3]">{fileName}</span> 有未保存的更改。如果不保存，更改将会丢失。
        </div>
        <div className="mt-4 flex justify-end gap-2">
          <button onClick={onCancel} className="rounded-md px-3 py-1.5 text-[12px] text-[#9a9590] transition-colors hover:bg-white/[0.06] hover:text-[#e8e6e3]">
            取消
          </button>
          <button onClick={onDiscard} className="rounded-md px-3 py-1.5 text-[12px] text-[#c97a76] transition-colors hover:bg-error/10">
            不保存
          </button>
          <button onClick={onSave} className="rounded-md bg-primary px-3 py-1.5 text-[12px] font-medium text-white transition-colors hover:bg-primary-hover">
            保存
          </button>
        </div>
      </div>
    </div>
  );
}
