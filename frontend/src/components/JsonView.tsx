export function JsonView({ data, label = "查看 payload" }: { data: unknown; label?: string }) {
  return (
    <details className="json-view">
      <summary>{label}</summary>
      <pre>{JSON.stringify(data, null, 2)}</pre>
    </details>
  );
}
