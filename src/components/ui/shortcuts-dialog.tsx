import { forwardRef } from "react"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog"
import { cn } from "@/lib/utils"

type ShortcutGroup = {
  title: string
  shortcuts: { keys: string[]; description: string }[]
}

const SHORTCUT_GROUPS: ShortcutGroup[] = [
  {
    title: "Navigation",
    shortcuts: [
      { keys: ["G", "D"], description: "Go to Dashboard" },
      { keys: ["G", "R"], description: "Go to Recovery Queue" },
      { keys: ["G", "A"], description: "Go to Analytics" },
      { keys: ["G", "S"], description: "Go to Simulator" },
      { keys: ["G", "U"], description: "Go to Audit Trail" },
      { keys: ["G", "P"], description: "Go to Policies" },
      { keys: ["G", "T"], description: "Go to Settings" },
    ],
  },
  {
    title: "Actions",
    shortcuts: [
      { keys: ["⌘", "K"], description: "Open command palette" },
      { keys: ["/"], description: "Focus search (command palette)" },
      { keys: ["?"], description: "View keyboard shortcuts" },
    ],
  },
  {
    title: "General",
    shortcuts: [
      { keys: ["Esc"], description: "Close dialog or panel" },
    ],
  },
]

function KeyBadge({ children }: { children: string }) {
  return (
    <kbd
      className={cn(
        "inline-flex h-6 min-w-[1.5rem] items-center justify-center rounded border border-border/60 bg-surface-low px-1.5",
        "font-mono text-[0.6875rem] font-medium text-muted-foreground",
        "shadow-[0_1px_0_0_var(--color-border)]"
      )}
    >
      {children}
    </kbd>
  )
}

interface ShortcutsDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export const ShortcutsDialog = forwardRef<HTMLDivElement, ShortcutsDialogProps>(
  function ShortcutsDialog({ open, onOpenChange }, _ref) {
    return (
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="sm:max-w-md gap-0 p-0">
          <DialogHeader className="px-6 pt-6 pb-0">
            <DialogTitle>Keyboard Shortcuts</DialogTitle>
            <DialogDescription>
              Navigate and act faster with keyboard shortcuts.
            </DialogDescription>
          </DialogHeader>

          <div className="px-6 py-5 space-y-5">
            {SHORTCUT_GROUPS.map((group) => (
              <div key={group.title}>
                <h3 className="text-[0.6875rem] font-medium uppercase tracking-wider text-faint mb-2.5">
                  {group.title}
                </h3>
                <div className="space-y-2">
                  {group.shortcuts.map((shortcut) => (
                    <div
                      key={shortcut.description}
                      className="flex items-center justify-between"
                    >
                      <span className="text-sm text-muted-foreground">
                        {shortcut.description}
                      </span>
                      <div className="flex items-center gap-1">
                        {shortcut.keys.map((key, i) => (
                          <span key={`${key}-${i}`} className="flex items-center gap-1">
                            {i > 0 && (
                              <span className="text-[0.625rem] text-faint">then</span>
                            )}
                            <KeyBadge>{key}</KeyBadge>
                          </span>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>

          <div className="border-t border-border px-6 py-3">
            <p className="text-[0.6875rem] text-faint text-center">
              <span className="text-muted-foreground">Tip:</span>{" "}
              <kbd className="rounded border border-border/60 bg-surface-low px-1 py-0.5 font-mono text-[0.625rem]">G</kbd>{" "}
              shortcuts work from any page — press <kbd className="rounded border border-border/60 bg-surface-low px-1 py-0.5 font-mono text-[0.625rem]">Esc</kbd> to cancel.
            </p>
          </div>
        </DialogContent>
      </Dialog>
    )
  }
)
