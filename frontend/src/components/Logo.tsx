import { cn } from "@/lib/utils"

/** The "candidate" wordmark; it takes the current text color. */
export function Logo({ className }: { className?: string }) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 -40 793 140" role="img" aria-label="Candidate" className={cn("h-5 w-auto", className)}>
      <g fill="none" stroke="currentColor" strokeWidth="17">
        <path d="M83.99 73.80A41.50 41.50 0 1 1 83.99 26.20" />
        <path d="M100.50 50.00a41.50 41.50 0 1 0 83.00 0a41.50 41.50 0 1 0 -83.00 0" />
        <path d="M183.50 50.00V100" />
        <path d="M205.50 100V46.00A37.50 37.50 0 0 1 280.50 46.00V100" />
        <path d="M302.50 50.00a41.50 41.50 0 1 0 83.00 0a41.50 41.50 0 1 0 -83.00 0" />
        <path d="M385.50 -40.00V100" />
        <path d="M407.50 0V100" />
        <path d="M429.50 50.00a41.50 41.50 0 1 0 83.00 0a41.50 41.50 0 1 0 -83.00 0" />
        <path d="M512.50 -40.00V100" />
        <path d="M534.50 50.00a41.50 41.50 0 1 0 83.00 0a41.50 41.50 0 1 0 -83.00 0" />
        <path d="M617.50 50.00V100" />
        <path d="M659.50 -30.00V100" />
        <path d="M631.00 8.50H688.00" />
        <path d="M778.19 71.99A41.50 41.50 0 1 1 784.50 50.00" />
        <circle cx="407.50" cy="-21.25" r="8.50" stroke="none" fill="currentColor" />
        <path d="M709.50 41.50H792.27A50.0 50.0 0 0 1 792.27 58.50H709.50Z" stroke="none" fill="currentColor" />
      </g>
    </svg>
  )
}
