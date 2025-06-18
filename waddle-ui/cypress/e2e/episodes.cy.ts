describe("Episodes E2E Test", () => {
	beforeEach(() => {
		cy.visit("/");
	});

	it("should create a new episode with audio files and delete it", () => {
		cy.get("body").should("not.contain", "Failed to fetch");

		// Create a new episode
		cy.contains("New Episode").click();

		cy.get('input[placeholder*="title"], input[name*="title"]').type(
			"Test Episode E2E",
		);

		const path = require("path");
		const audioFileNames = [
			"ep12-kotaro.wav",
			"ep12-masa.wav",
			"ep12-shun.wav",
			"GMT20250119-015233_Recording_1280x720.wav",
		];
		const audioFiles = audioFileNames.map((fileName) =>
			path.resolve(
				Cypress.config("projectRoot"),
				"..",
				"waddle-api",
				"tests",
				"ep0",
				fileName,
			),
		);
		cy.get('input[type="file"]').selectFile(audioFiles, { force: true });

		cy.contains("Create Episode").click();

		cy.contains("Test Episode E2E").should("be.visible");
		cy.contains("Preprocess", { timeout: 60000 }).should("be.visible");
		cy.get('[data-testid="preprocess-status"], input[type="checkbox"]').should(
			"be.checked",
			{ timeout: 300000 },
		);

		cy.screenshot("episode-created-with-preprocess-complete");

		cy.contains("Delete").click();

		// Confirm deletion if there's a confirmation dialog
		cy.get("body").then(($body) => {
			if (
				$body.find('[data-testid="confirm-delete"], button:contains("Confirm")')
					.length > 0
			) {
				cy.contains("Confirm").click();
			}
		});

		cy.contains("Test Episode E2E").should("not.exist");
	});
});
