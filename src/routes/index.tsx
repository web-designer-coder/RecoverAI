import { createFileRoute } from "@tanstack/react-router";
import { SiteNavbar, SiteFooter } from "@/components/site-nav";
import { Toaster } from "@/components/ui/sonner";
import {
  Hero,
  Problem,
  Workflow,
  DecisionShowcase,
  Comparison,
  Guardrails,
  ProductPreview,
  SimulatorTeaser,
  FinalCta,
} from "@/components/landing/sections-a";

export const Route = createFileRoute("/")({
  component: Index,
});

function Index() {
  return (
    <div className="min-h-screen bg-background pt-16">
      <SiteNavbar />
      <main>
        <Hero />
        <Problem />
        <Workflow />
        <DecisionShowcase />
        <Comparison />
        <Guardrails />
        <ProductPreview />
        <SimulatorTeaser />
        <FinalCta />
      </main>
      <SiteFooter />
      <Toaster
        position="bottom-right"
        toastOptions={{
          duration: 4000,
          style: {
            background: "var(--color-surface)",
            border: "1px solid var(--color-border)",
            color: "var(--color-foreground)",
          },
        }}
      />
    </div>
  );
}
