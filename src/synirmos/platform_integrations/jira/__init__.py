"""Future Jira issue-tracker integration; no Git-hosting responsibilities."""


class JiraIntegration:
    """Unimplemented extension marker; Jira issues need no Git repository identity."""

    def __init__(self) -> None:
        raise NotImplementedError("Jira integration is a placeholder, not an available provider")
