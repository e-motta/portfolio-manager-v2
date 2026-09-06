type AlertProps = {
  tone?: "ok" | "error" | "warn";
  children: React.ReactNode;
};

export function Alert({ tone = "ok", children }: AlertProps) {
  return (
    <div className={`alert alert--${tone}`} role={tone === "error" ? "alert" : "status"}>
      <div className="alert-body">{children}</div>
    </div>
  );
}
