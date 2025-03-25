import { createFileRoute, Link as RouterLink } from "@tanstack/react-router";
import { useEffect, useState, useCallback, useRef } from "react";
import {
	Box,
	Heading,
	Text,
	VStack,
	HStack,
	Spinner,
	Card,
	Badge,
	Flex,
	Button,
	Alert,
	Dialog,
} from "@chakra-ui/react";
import { toaster } from "../components/ui/toaster";
import {
	type Episode,
	readEpisodesV1EpisodesGet,
	deleteEpisodeV1EpisodesEpisodeIdDelete,
} from "../client";

export const Route = createFileRoute("/")({
	component: Index,
});

function Index() {
	const [episodes, setEpisodes] = useState<Episode[]>([]);
	const [loading, setLoading] = useState(true);
	const [error, setError] = useState<string | null>(null);
	const [episodeToDelete, setEpisodeToDelete] = useState<string | null>(null);
	const [episodeTitle, setEpisodeTitle] = useState<string | null>(null);
	const [isDialogOpen, setIsDialogOpen] = useState(false);
	const [isDeleting, setIsDeleting] = useState(false);

	// Ref for the cancel button to return focus to
	const cancelRef = useRef(null);

	const fetchEpisodes = useCallback(async () => {
		try {
			setLoading(true);
			const response = await readEpisodesV1EpisodesGet();
			if (response.error) {
				throw new Error("Failed to fetch episodes");
			}
			setEpisodes(response.data || []);
			console.log(response.data);
		} catch (err) {
			setError(
				err instanceof Error ? err.message : "An unknown error occurred",
			);
		} finally {
			setLoading(false);
		}
	}, []);

	useEffect(() => {
		fetchEpisodes();
	}, [fetchEpisodes]);

	const handleDeleteClick = (episodeId: string, title?: string) => {
		setEpisodeToDelete(episodeId);
		setEpisodeTitle(title || "Untitled Episode");
		setIsDialogOpen(true);
	};

	const confirmDelete = async () => {
		if (!episodeToDelete) return;

		try {
			setIsDeleting(true);
			const response = await deleteEpisodeV1EpisodesEpisodeIdDelete({
				path: { episode_id: episodeToDelete },
			});

			if (response.error) {
				throw new Error("Failed to delete episode");
			}

			// Update local state to remove the deleted episode
			setEpisodes(
				episodes.filter((episode) => episode.uuid !== episodeToDelete),
			);

			// Show success notification
			toaster.create({
				description: `Episode "${episodeTitle}" deleted successfully`,
				type: "success",
			});
		} catch (err) {
			toaster.create({
				description:
					err instanceof Error ? err.message : "Failed to delete episode",
				type: "error",
			});
		} finally {
			setIsDeleting(false);
			setIsDialogOpen(false);
			setEpisodeToDelete(null);
			setEpisodeTitle(null);
		}
	};

	const formatDate = (dateString?: string) => {
		if (!dateString) return "Unknown date";
		return new Date(dateString).toLocaleDateString(undefined, {
			year: "numeric",
			month: "short",
			day: "numeric",
		});
	};

	return (
		<Box p={4}>
			<Flex justifyContent="space-between" alignItems="center" mb={4}>
				<Heading size="lg">Episodes</Heading>
				<RouterLink to="/episodes/new">
					<Button colorScheme="blue">New Episode</Button>
				</RouterLink>
			</Flex>

			{loading ? (
				<Flex justifyContent="center" p={8}>
					<Spinner size="xl" />
				</Flex>
			) : error ? (
				<Alert.Root status="error">
					<Alert.Indicator />
					<Alert.Content>
						<Alert.Description>{error}</Alert.Description>
					</Alert.Content>
				</Alert.Root>
			) : episodes.length === 0 ? (
				<Text p={4}>No episodes found. Create your first episode!</Text>
			) : (
				<VStack gap={4} align="stretch">
					{episodes.map((episode) => (
						<Card.Root key={episode.uuid} variant="outline">
							<Card.Header>
								<Flex justifyContent="space-between" alignItems="center">
									<Heading size="md">
										{episode.title || "Untitled Episode"}
									</Heading>
									<Text fontSize="sm" color="gray.500">
										Created: {formatDate(episode.created_at)}
									</Text>
								</Flex>
							</Card.Header>
							<Card.Body>
								<HStack gap={2}>
									<Badge
										colorScheme={episode.preprocessed ? "green" : "yellow"}
									>
										{episode.preprocessed ? "Preprocessed" : "Preprocessing"}
									</Badge>
									<Badge
										colorScheme={episode.postprocessed ? "green" : "yellow"}
									>
										{episode.postprocessed ? "Postprocessed" : "Postprocessing"}
									</Badge>
									<Badge
										colorScheme={episode.metadata_generated ? "green" : "gray"}
									>
										{episode.metadata_generated
											? "Metadata Generated"
											: "No Metadata"}
									</Badge>
								</HStack>
							</Card.Body>
							<Card.Footer>
								<Flex justifyContent="flex-end">
									{episode.uuid && (
										<RouterLink
											to="/episodes/$episodeId"
											params={{ episodeId: episode.uuid }}
										>
											<Button size="sm" colorScheme="blue" mr={2}>
												Edit
											</Button>
										</RouterLink>
									)}
									<Button
										size="sm"
										colorScheme="red"
										onClick={() =>
											episode.uuid &&
											handleDeleteClick(episode.uuid, episode.title)
										}
									>
										Delete
									</Button>
								</Flex>
							</Card.Footer>
						</Card.Root>
					))}
				</VStack>
			)}

			{/* Delete Confirmation Dialog */}
			<Dialog.Root
				open={isDialogOpen}
				onOpenChange={({ open }) => setIsDialogOpen(open)}
				size="sm"
				placement="center"
				motionPreset="slide-in-bottom"
				role="alertdialog"
				closeOnEscape={false}
				closeOnInteractOutside={false}
				finalFocusEl={() => cancelRef.current}
			>
				<Dialog.Backdrop />
				<Dialog.Positioner>
					<Dialog.Content>
						<Dialog.CloseTrigger />
						<Dialog.Header>
							<Dialog.Title>Confirm Episode Deletion</Dialog.Title>
						</Dialog.Header>
						<Dialog.Body>
							<Text>
								Are you sure you want to delete "{episodeTitle}"? This action
								cannot be undone.
							</Text>
						</Dialog.Body>
						<Dialog.Footer>
							<Button
								ref={cancelRef}
								variant="outline"
								mr={3}
								onClick={() => setIsDialogOpen(false)}
								isDisabled={isDeleting}
							>
								Cancel
							</Button>
							<Button
								colorScheme="red"
								onClick={confirmDelete}
								isLoading={isDeleting}
								loadingText="Deleting"
							>
								Delete
							</Button>
						</Dialog.Footer>
					</Dialog.Content>
				</Dialog.Positioner>
			</Dialog.Root>
		</Box>
	);
}
