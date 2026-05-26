interface PromptMomentNotification {
  isNotDisplayed(): boolean
  isSkippedMoment(): boolean
  isDismissedMoment(): boolean
  getNotDisplayedReason(): string
  getSkippedReason(): string
  getDismissedReason(): string
}

interface Window {
  google?: {
    accounts: {
      id: {
        initialize(config: {
          client_id: string
          callback: (response: { credential: string }) => void
          auto_select?: boolean
        }): void
        prompt(momentListener?: (notification: PromptMomentNotification) => void): void
        cancel(): void
        disableAutoSelect(): void
      }
    }
  }
}
