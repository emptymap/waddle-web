import { createFileRoute, Link as RouterLink } from "@tanstack/react-router";
import { useEffect, useState, useCallback, useRef } from "react";
import {
	Box,
	Heading,
	Text,
	VStack,
	Spinner,
	Card,
	Flex,
	Button,
	Alert,
	Dialog,
	Steps,
} from "@chakra-ui/react";
import { toaster } from "../components/ui/toaster";
import {
	Check,
	AudioLines,
	Captions,
	FilePenLine,
	PlusCircle,
	Edit,
	Trash2,
	X,
	AlertTriangle,
} from "lucide-react";
import {
	type Episode,
	JobStatus,
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

	// Calculate the current step for each episode
	const getEpisodeStep = (episode: Episode) => {
		if (episode.metadata_generation_status === JobStatus.COMPLETED) return 3;
		if (episode.postprocess_status === JobStatus.COMPLETED) return 2;
		if (episode.preprocess_status === JobStatus.COMPLETED) return 1;
		return 0; // No steps complete
	};

	// Define the processing steps
	const processingSteps = [
		{
			title: "Preprocessing",
			description: "Initial data processing",
			icon: <AudioLines />,
		},
		{
			title: "Postprocessing",
			description: "Secondary data processing",
			icon: <Captions />,
		},
		{
			title: "Metadata",
			description: "Metadata generation",
			icon: <FilePenLine />,
		},
	];

	return (
		<Box p={4}>
			<Flex justifyContent="space-between" alignItems="center" mb={4}>
				<Heading size="lg">Episodes</Heading>
				<RouterLink to="/episodes/new">
					<Button>
						<PlusCircle size={16} /> New Episode
					</Button>
				</RouterLink>
			</Flex>

			{loading ? (
				<Flex justifyContent="center" p={8}>
					<Spinner size="xl" />
				</Flex>
			) : error ? (
				<Alert.Root status="error">
					<Alert.Indicator>
						<AlertTriangle />
					</Alert.Indicator>
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
								{/* Steps component to replace badges */}
								<Steps.Root
									step={getEpisodeStep(episode)}
									count={processingSteps.length}
									size="sm"
									variant="solid"
								>
									<Steps.List>
										{processingSteps.map((step, index) => (
											<Steps.Item key={step.title} index={index} gap={2}>
												<Steps.Indicator>
													<Steps.Status
														incomplete={step.icon}
														complete={<Check />}
													/>
												</Steps.Indicator>
												<Steps.Title>{step.title}</Steps.Title>
												<Steps.Separator />
											</Steps.Item>
										))}
									</Steps.List>
								</Steps.Root>
							</Card.Body>
							<Card.Footer>
								<Flex justifyContent="flex-end">
									{episode.uuid && (
										<RouterLink
											to="/episodes/$episodeId"
											params={{ episodeId: episode.uuid }}
										>
											<Button size="sm" mr={2}>
												<Edit size={14} /> Edit
											</Button>
										</RouterLink>
									)}
									<Button
										size="sm"
										onClick={() =>
											episode.uuid &&
											handleDeleteClick(episode.uuid, episode.title)
										}
									>
										<Trash2 size={14} /> Delete
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
								loading={isDeleting}
							>
								<X size={16} /> Cancel
							</Button>
							<Button
								colorPalette="red"
								onClick={confirmDelete}
								loading={isDeleting}
								loadingText="Deleting"
							>
								<Trash2 size={16} /> Delete
							</Button>
						</Dialog.Footer>
					</Dialog.Content>
				</Dialog.Positioner>
			</Dialog.Root>
		</Box>
	);
}
