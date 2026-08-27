import React, { useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import {
  AlertTriangleIcon,
  FolderIcon,
  HexagonIcon,
  RocketIcon,
  ShieldCheckIcon,
  SparklesIcon } from
'lucide-react';
import { LaunchConfig } from '../../types/mission';

interface LaunchScreenProps {
  onLaunch: (config: LaunchConfig) => void;
}

const DEFAULT_SPEC = `Return only the latest five transactions belonging to the authorized user.

- Enforce ownership before reading transaction history.
- Return at most the five most recent transactions.
- Keep the public service API backwards compatible.`;

const DEFAULT_TEST_SPEC = `Verify with pytest:
- the five-item response limit
- latest-first ordering
- cross-user access is rejected`;

const ease = [0.23, 1, 0.32, 1] as const;

export function LaunchScreen({ onLaunch }: LaunchScreenProps) {
  const [projectPath, setProjectPath] = useState('sample_app');
  const [specification, setSpecification] = useState(DEFAULT_SPEC);
  const [testSpecification, setTestSpecification] = useState(DEFAULT_TEST_SPEC);
  const [authorized, setAuthorized] = useState(false);
  const [confirmed, setConfirmed] = useState(false);

  const needsConfirm = authorized && !confirmed;
  const canLaunch = projectPath.trim().length > 0 && specification.trim().length > 0 && !needsConfirm;

  const toggle = () => {
    setAuthorized((prev) => {
      if (prev) setConfirmed(false);
      return !prev;
    });
    setConfirmed(false);
  };

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!canLaunch) return;
    onLaunch({
      projectPath: projectPath.trim(),
      specification,
      testSpecification,
      writeMode: authorized ? 'authorized' : 'dry_run'
    });
  };

  return (
    <div className="circuit-grid min-h-screen w-full px-5 py-10 md:px-10 md:py-14">
      <div className="mx-auto w-full max-w-6xl">
        <div className="flex flex-wrap items-end justify-between gap-6">
          <div>
            <div className="mb-3 flex items-center gap-2.5">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg border border-electric/40 bg-electric/10">
                <HexagonIcon className="h-4 w-4 text-electric" strokeWidth={2.2} />
              </div>
              <span className="font-mono text-[11px] uppercase tracking-[0.28em] text-electric/80">
                orchestrator v2.4
              </span>
            </div>
            <h1 className="text-4xl font-semibold tracking-tight text-slate-50 md:text-5xl">
              Launch a run
            </h1>
            <p className="mt-3 max-w-xl text-sm leading-relaxed text-mist">
              Six agents will negotiate this specification across up to three iterations. You keep the
              write gate.
            </p>
          </div>
          <dl className="grid grid-cols-3 gap-x-8 gap-y-1 font-mono text-[11px] text-mist/70">
            <div>
              <dt className="uppercase tracking-[0.16em] text-mist/50">agents</dt>
              <dd className="text-lg text-slate-100">6</dd>
            </div>
            <div>
              <dt className="uppercase tracking-[0.16em] text-mist/50">max iter</dt>
              <dd className="text-lg text-slate-100">3</dd>
            </div>
            <div>
              <dt className="uppercase tracking-[0.16em] text-mist/50">provider</dt>
              <dd className="text-lg text-neon">local</dd>
            </div>
          </dl>
        </div>

        <form
          onSubmit={submit}
          className="mt-10 grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
          
          <div className="glass rounded-2xl p-6 shadow-panel md:p-7">
            <label className="block">
              <span className="mb-2 block text-[11px] font-medium uppercase tracking-[0.18em] text-mist/70">
                Project path
              </span>
              <div className="group flex items-center gap-3 rounded-lg border border-hull-400/60 bg-hull-900/70 px-3.5 py-2.5 transition-colors duration-200 ease-command focus-within:border-electric/60">
                <FolderIcon className="h-4 w-4 shrink-0 text-electric/80" />
                <input
                  value={projectPath}
                  onChange={(e) => setProjectPath(e.target.value)}
                  spellCheck={false}
                  className="w-full bg-transparent font-mono text-sm text-slate-100 outline-none placeholder:text-mist/40"
                  placeholder="sample_app" />
                
              </div>
            </label>

            <label className="mt-6 block">
              <span className="mb-2 flex items-baseline justify-between text-[11px] font-medium uppercase tracking-[0.18em] text-mist/70">
                Specification
                <span className="font-mono text-[10px] normal-case tracking-normal text-mist/45">
                  {specification.trim().length} chars
                </span>
              </span>
              <textarea
                value={specification}
                onChange={(e) => setSpecification(e.target.value)}
                rows={9}
                spellCheck={false}
                className="thin-scroll w-full resize-y rounded-lg border border-hull-400/60 bg-hull-900/70 px-3.5 py-3 font-mono text-[13px] leading-relaxed text-slate-200 outline-none transition-colors duration-200 ease-command focus:border-electric/60 placeholder:text-mist/40"
                placeholder="Describe what the agents should build or change..." />
              
            </label>

            <label className="mt-5 block">
              <span className="mb-2 flex items-baseline gap-2 text-[11px] font-medium uppercase tracking-[0.18em] text-mist/70">
                Test specification
                <span className="rounded border border-hull-400/60 px-1.5 py-0.5 font-mono text-[9px] normal-case tracking-normal text-mist/50">
                  optional
                </span>
              </span>
              <textarea
                value={testSpecification}
                onChange={(e) => setTestSpecification(e.target.value)}
                rows={5}
                spellCheck={false}
                className="thin-scroll w-full resize-y rounded-lg border border-hull-400/60 bg-hull-900/70 px-3.5 py-3 font-mono text-[13px] leading-relaxed text-slate-200 outline-none transition-colors duration-200 ease-command focus:border-electric/60 placeholder:text-mist/40"
                placeholder="How should the Testing agent verify the work?" />
              
            </label>
          </div>

          <div className="flex flex-col gap-6">
            <div
              className={`glass rounded-2xl p-6 shadow-panel transition-shadow duration-300 ease-command ${
              authorized ? 'shadow-glow-alert' : 'shadow-glow-amber'}`
              }>
              
              <div className="flex items-start justify-between gap-4">
                <div>
                  <h2 className="text-sm font-semibold text-slate-100">Write gate</h2>
                  <p
                    className={`mt-1 font-mono text-[11px] uppercase tracking-[0.16em] ${
                    authorized ? 'text-alert' : 'text-amber'}`
                    }>
                    
                    {authorized ? 'authorize writes' : 'dry run'}
                  </p>
                </div>
                <button
                  type="button"
                  role="switch"
                  aria-checked={authorized}
                  aria-label="Toggle between dry run and authorized writes"
                  onClick={toggle}
                  className={`relative h-7 w-14 shrink-0 rounded-full border transition-colors duration-200 ease-command ${
                  authorized ?
                  'border-alert/60 bg-alert/20 shadow-glow-alert' :
                  'border-amber/60 bg-amber/15 shadow-glow-amber'}`
                  }>
                  
                  <motion.span
                    layout
                    transition={{ duration: 0.22, ease }}
                    className={`absolute top-1/2 h-5 w-5 -translate-y-1/2 rounded-full ${
                    authorized ? 'left-8 bg-alert' : 'left-1 bg-amber'}`
                    } />
                  
                </button>
              </div>

              <p className="mt-4 text-[12px] leading-relaxed text-mist/80">
                Dry run previews generated code without touching your project.
              </p>

              <AnimatePresence initial={false}>
                {authorized &&
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  exit={{ opacity: 0, height: 0 }}
                  transition={{ duration: 0.24, ease }}
                  className="overflow-hidden">
                  
                    <div className="mt-4 rounded-lg border border-alert/35 bg-alert/[0.07] p-3.5">
                      <div className="flex items-start gap-2.5">
                        <AlertTriangleIcon className="mt-0.5 h-4 w-4 shrink-0 text-alert" />
                        <p className="text-[12px] leading-relaxed text-slate-200">
                          Agents will write real files into an isolated workspace copy of{' '}
                          <span className="font-mono text-alert">{projectPath || 'your project'}</span>.
                        </p>
                      </div>
                      <button
                      type="button"
                      onClick={() => setConfirmed(true)}
                      disabled={confirmed}
                      className={`mt-3 w-full rounded-md border px-3 py-2 font-mono text-[11px] uppercase tracking-[0.16em] transition-colors duration-200 ease-command ${
                      confirmed ?
                      'cursor-default border-neon/45 bg-neon/10 text-neon' :
                      'border-alert/50 bg-alert/15 text-alert hover:bg-alert/25'}`
                      }>
                      
                        {confirmed ? 'write access confirmed' : 'confirm write access'}
                      </button>
                    </div>
                  </motion.div>
                }
              </AnimatePresence>
            </div>

            <div className="glass-soft rounded-2xl p-5">
              <h3 className="flex items-center gap-2 text-[11px] font-medium uppercase tracking-[0.18em] text-mist/70">
                <SparklesIcon className="h-3.5 w-3.5 text-plasma" />
                Pre-flight
              </h3>
              <ul className="mt-3 space-y-2 font-mono text-[11px] text-mist/80">
                <li className="flex items-center gap-2">
                  <ShieldCheckIcon className="h-3.5 w-3.5 text-neon" /> MCP · runtime discovery
                </li>
                <li className="flex items-center gap-2">
                  <ShieldCheckIcon className="h-3.5 w-3.5 text-neon" /> RAG · runtime retrieval
                </li>
                <li className="flex items-center gap-2">
                  <ShieldCheckIcon className="h-3.5 w-3.5 text-neon" /> Ollama · qwen3.5:4b / qwen3.5:9b
                </li>
              </ul>
            </div>

            <button
              type="submit"
              disabled={!canLaunch}
              className="group relative flex w-full items-center justify-center gap-3 overflow-hidden rounded-xl border border-electric/50 bg-electric/15 px-6 py-4 text-base font-semibold tracking-tight text-slate-50 shadow-glow-electric transition-colors duration-200 ease-command hover:bg-electric/25 disabled:cursor-not-allowed disabled:border-hull-400/60 disabled:bg-hull-700/60 disabled:text-mist/50 disabled:shadow-none">
              
              <RocketIcon className="h-5 w-5 text-electric transition-transform duration-200 ease-command group-hover:-translate-y-0.5 group-disabled:text-mist/50" />
              Launch Run
            </button>
            {needsConfirm &&
            <p className="-mt-3 text-center font-mono text-[11px] text-alert">
                confirm write access to continue
              </p>
            }
          </div>
        </form>
      </div>
    </div>);

}
