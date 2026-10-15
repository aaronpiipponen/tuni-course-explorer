/** Shared placeholder rows shown while a course or module lookup request is in flight. */
export function LookupSkeletons({ label }: { label: string }) {
  return (
    <div className="course-lookup-skeletons" aria-label={label}>
      {Array.from({ length: 5 }, (_, index) => (
        <div className="course-lookup-skeleton" key={index} />
      ))}
    </div>
  );
}
