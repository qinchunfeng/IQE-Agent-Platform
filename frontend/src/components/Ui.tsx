import type { ReactNode } from "react";
import { Icon } from "../Icon";
import { statusLabel, statusTone, type Tone } from "../utils";

export function Badge({ children, tone = "neutral" }: { children: ReactNode; tone?: Tone }) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}

export function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`badge badge-${statusTone(status)}`}>
      <span className="badge-dot" />
      {statusLabel(status)}
    </span>
  );
}

interface StatCardProps {
  title: string;
  value: ReactNode;
  hint?: ReactNode;
  icon: "traces" | "check" | "clock" | "ticket" | "knowledge" | "cpu" | "layers" | "shield";
  accent?: "blue" | "green" | "amber" | "violet" | "rose";
}

export function StatCard({ title, value, hint, icon, accent = "blue" }: StatCardProps) {
  return (
    <div className={`stat-card accent-${accent}`}>
      <div className="stat-icon">
        <Icon name={icon} size={20} />
      </div>
      <div className="stat-body">
        <div className="stat-title">{title}</div>
        <div className="stat-value">{value}</div>
        {hint ? <div className="stat-hint">{hint}</div> : null}
      </div>
    </div>
  );
}

interface SectionCardProps {
  title?: ReactNode;
  subtitle?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}

export function SectionCard({ title, subtitle, action, children, className = "" }: SectionCardProps) {
  return (
    <section className={`card ${className}`}>
      {title || action ? (
        <div className="card-head">
          <div>
            {title ? <h2>{title}</h2> : null}
            {subtitle ? <p>{subtitle}</p> : null}
          </div>
          {action ? <div className="card-action">{action}</div> : null}
        </div>
      ) : null}
      {children}
    </section>
  );
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="empty-state">
      <div className="empty-mark">
        <Icon name="spark" size={24} />
      </div>
      <h3>{title}</h3>
      {description ? <p>{description}</p> : null}
      {action}
    </div>
  );
}

export function Spinner({ label }: { label?: string }) {
  return (
    <span className="spinner-wrap">
      <span className="spinner" />
      {label ? <span>{label}</span> : null}
    </span>
  );
}

export function ConfidenceMeter({ value }: { value: number | null | undefined }) {
  if (value === null || value === undefined) return <span className="muted">—</span>;
  const percent = Math.max(0, Math.min(100, value * 100));
  const tone = value < 0.7 ? "danger" : value < 0.85 ? "warning" : "success";
  return (
    <div className="confidence">
      <div className="confidence-track">
        <div className={`confidence-fill fill-${tone}`} style={{ width: `${percent}%` }} />
      </div>
      <span className="confidence-value">{(value * 100).toFixed(0)}%</span>
    </div>
  );
}

interface ModalProps {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
}

export function Modal({ open, title, onClose, children, footer }: ModalProps) {
  if (!open) return null;
  return (
    <div className="modal-mask" role="presentation" onMouseDown={onClose}>
      <div className="modal" role="dialog" aria-modal="true" onMouseDown={(event) => event.stopPropagation()}>
        <div className="modal-head">
          <h3>{title}</h3>
          <button className="icon-button" onClick={onClose} aria-label="关闭">
            <Icon name="close" size={18} />
          </button>
        </div>
        <div className="modal-body">{children}</div>
        {footer ? <div className="modal-footer">{footer}</div> : null}
      </div>
    </div>
  );
}
