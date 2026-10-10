import { useEffect, useRef } from "react"

import { SignInWithVercelButton } from "@/components/auth/sign-in-with-vercel"

import styles from "./landing-page.module.css"

const GITHUB = "https://github.com/vigneshm1995personal/skillgate-ai"
const AUTH = "/api/auth/authorize"

export function LandingPage({ configured }: { configured?: boolean }) {
  const storyRef = useRef<HTMLDivElement>(null)
  const closerRef = useRef<HTMLElement>(null)

  useEffect(() => {
    const nodes = [
      ...(storyRef.current?.querySelectorAll<HTMLElement>(
        `.${styles.band}, .${styles.bandDual}`,
      ) ?? []),
      ...(closerRef.current ? [closerRef.current] : []),
    ]

    nodes.forEach((el) => el.classList.add(styles.reveal))

    const reduceMotion = window.matchMedia(
      "(prefers-reduced-motion: reduce)",
    ).matches

    if (reduceMotion || !("IntersectionObserver" in window)) {
      nodes.forEach((el) => el.classList.add(styles.inView))
      return
    }

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting && entry.intersectionRatio >= 0.18) {
            entry.target.classList.add(styles.inView)
            observer.unobserve(entry.target)
          }
        })
      },
      { threshold: [0.18] },
    )

    nodes.forEach((el) => observer.observe(el))
    return () => observer.disconnect()
  }, [])

  const signInGhost =
    configured === false ? null : (
      <SignInWithVercelButton
        className={[styles.btn, styles.btnGhost].join(" ")}
      />
    )

  const getStarted =
    configured === false ? (
      <p className={styles.unavailable}>
        Sign in isn’t available on this deployment. Contact the admin.
      </p>
    ) : (
      <a className={[styles.btn, styles.btnPrimary].join(" ")} href={AUTH}>
        Get started
      </a>
    )

  const getStartedOrNull =
    configured === false ? null : (
      <a className={[styles.btn, styles.btnPrimary].join(" ")} href={AUTH}>
        Get started
      </a>
    )

  return (
    <div className={styles.root}>
      <nav className={styles.nav}>
        <div className={styles.logo}>Skill Gate</div>
        <div className={styles.navLinks}>
          {signInGhost}
          {getStartedOrNull}
        </div>
      </nav>

      <main>
        <section className={styles.hero}>
          <h1>Evaluate. Gate. Deploy.</h1>
          <p className={styles.lede}>Checks run before install.</p>
          <div className={styles.ctaRow}>
            {getStarted}
            {signInGhost}
          </div>
        </section>

        <div className={styles.heroShot}>
          <div className={styles.frame}>
            <img
              src="/landing/f-checks-fail-why.png"
              alt="Skill Gate — Gate Fail with expanded WHY"
              width={887}
              height={451}
            />
          </div>
          <p className={styles.cap}>
            Gate · Fail · WHY expanded
            <span className={styles.tag}>Blocked</span>
          </p>
        </div>

        <div className={styles.story} ref={storyRef}>
          <section className={styles.band} aria-labelledby="band-cases">
            <div className={styles.bandCopy}>
              <h2 id="band-cases">Generate the Dataset</h2>
              <p>Skill Gate proposes checks and prompts from the skill.</p>
            </div>
            <div className={styles.bandVisual}>
              <div className={styles.frame}>
                <img
                  src="/landing/f-test-suite.png"
                  alt="Generated Dataset checks"
                  width={780}
                  height={455}
                />
              </div>
            </div>
          </section>

          <section className={styles.band} aria-labelledby="band-eval">
            <div className={styles.bandCopy}>
              <h2 id="band-eval">Run the checks</h2>
              <p>Run the Dataset. Pass means each check cleared.</p>
            </div>
            <div className={styles.bandVisual}>
              <div className={styles.frame}>
                <img
                  src="/landing/f-checks-pass.png"
                  alt="Checks Pass list — five green Pass rows"
                  width={945}
                  height={456}
                />
              </div>
            </div>
          </section>

          <section
            className={`${styles.band} ${styles.bandReverse}`}
            aria-labelledby="band-gate"
          >
            <div className={styles.bandCopy}>
              <h2 id="band-gate">Read the fail</h2>
              <p>Expand a failed row for the reason.</p>
            </div>
            <div className={styles.bandVisual}>
              <div className={styles.frame}>
                <img
                  src="/landing/f-checks-fail-why.png"
                  alt="Gate Fail WHY expanded row"
                  width={887}
                  height={451}
                />
              </div>
            </div>
          </section>

          <section className={styles.band} aria-labelledby="band-deploy">
            <div className={styles.bandCopy}>
              <h2 id="band-deploy">Ship when clear</h2>
              <p>Install to Cursor, Codex, or Claude only after checks pass.</p>
            </div>
            <div className={styles.bandVisual}>
              <div className={styles.frame}>
                <img
                  src="/landing/f-deploy.png"
                  alt="Deploy panel — blocked until gate is green"
                  width={945}
                  height={520}
                />
              </div>
            </div>
          </section>

          <section className={styles.bandDual} aria-labelledby="band-trail">
            <div className={styles.bandDualHead}>
              <h2 id="band-trail">Keep the trail</h2>
              <p>
                Each version has a pack hash. Deploys and fails show in History.
              </p>
            </div>
            <div className={styles.dualGrid}>
              <div>
                <div className={styles.frame}>
                  <img
                    src="/landing/f-skill-versions.png"
                    alt="Skill Versions — semver and pack hash"
                    width={465}
                    height={354}
                  />
                </div>
                <p className={styles.dualLabel}>Versions · semver + pack hash</p>
              </div>
              <div>
                <div className={styles.frame}>
                  <img
                    src="/landing/f-deploy-history.png"
                    alt="History — Fail and Deploy events"
                    width={1024}
                    height={525}
                  />
                </div>
                <p className={styles.dualLabel}>History · Fail + Deploy events</p>
              </div>
            </div>
          </section>
        </div>

        <section className={styles.closer} ref={closerRef}>
          <p>Deploy after a pass.</p>
          <div className={styles.ctaRow}>{getStartedOrNull}</div>
        </section>
      </main>

      <footer className={styles.footer}>
        <div className={styles.footerInner}>
          <span>Skill Gate</span>
          <a href={GITHUB} rel="noreferrer" target="_blank">
            Open source on GitHub
          </a>
        </div>
      </footer>
    </div>
  )
}
