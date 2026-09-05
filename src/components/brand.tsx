import { cn } from "@/lib/utils";

export function LogoMark({ className }: { className?: string }) {
  return (
    <img
      src="/brand/recoverai-coins.gif"
      alt=""
      aria-hidden="true"
      width={28}
      height={28}
      className={cn("shrink-0 object-contain", className)}
    />
  );
}

export function Logo({ className }: { className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-2", className)}>
      <LogoMark />
      <span className="font-display text-[1.25rem] font-semibold tracking-[-0.025em] text-foreground leading-none">
        Recover<span className="font-extrabold tracking-[-0.03em] text-foreground">AI</span>
      </span>
    </span>
  );
}

export function LandingLogo({
  className,
  size = 'landing'
}: {
  className?: string;
  size?: 'landing' | 'auth' | 'app'
}) {
  const sizeMap = {
    landing: 'text-[2rem]', // 32px
    auth: 'text-[1.5rem]',  // 24px (within 22-26px)
    app: 'text-[1.125rem]', // 18px
  };
  const iconSizeMap = {
    landing: 'w-9 h-9',
    auth: 'w-7 h-7',
    app: 'w-5 h-5',
  };

  return (
    <span className={cn("inline-flex items-center gap-3", className)}>
      <LogoMark className={cn(iconSizeMap[size as keyof typeof iconSizeMap])} />
      <span className="flex items-baseline gap-0">
        <span className={cn(
          "font-[family-name:var(--font-wordmark)] font-semibold italic tracking-[-0.02em] leading-none [text-shadow:0_1px_0_rgba(0,0,0,0.12)]",
          sizeMap[size as keyof typeof sizeMap],
          "text-[#D99A00]"
        )}>
          Recover
        </span>
        <span className={cn(
          "font-[family-name:var(--font-wordmark)] font-semibold italic tracking-[-0.02em] leading-none [text-shadow:0_1px_0_rgba(0,0,0,0.12)]",
          sizeMap[size as keyof typeof sizeMap],
          "text-[#D99A00]"
        )}>
          AI
        </span>
      </span>
    </span>
  );
}
