import { LinkButton } from "../../components/common/Button";
import { PageHeader } from "../../components/layout/PageHeader";

export function NotFound() {
  return (
    <>
      <PageHeader title="Page not found" lead="This address does not exist in the CLINVEIL interface." />
      <LinkButton to="/" variant="secondary">
        Back to the home page
      </LinkButton>
    </>
  );
}
