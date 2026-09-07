type EmptyStateProps = {
  title: string;
  body?: string;
};

export function EmptyState({ title, body }: EmptyStateProps) {
  return (
    <div className="empty-block">
      <p className="empty-block__title">{title}</p>
      {body ? <p>{body}</p> : null}
    </div>
  );
}
