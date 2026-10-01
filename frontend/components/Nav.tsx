"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/", label: "Summary" },
  { href: "/vendors", label: "Vendors" },
  { href: "/not-vendor", label: "Not the vendor" },
  { href: "/gaps", label: "Gaps" },
  { href: "/try", label: "Try a comment" },
];

export function Nav() {
  const pathname = usePathname();
  return (
    <nav className="nav" aria-label="Main">
      <span className="brand">Dhaga &amp; Co. · Returns Insight</span>
      <ul>
        {LINKS.map(({ href, label }) => {
          const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
          return (
            <li key={href}>
              <Link href={href} aria-current={active ? "page" : undefined}>
                {label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
