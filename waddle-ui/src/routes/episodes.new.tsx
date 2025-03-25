import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useForm } from "react-hook-form";
import {
	Box,
	Button,
	Heading,
	Input,
	VStack,
	Flex,
	SimpleGrid,
	Card,
	Field,
	Text,
} from "@chakra-ui/react";
import { toaster } from "../components/ui/toaster";
import { createEpisodeV1EpisodesPost } from "../client";
import { useState, useRef } from "react";
import { ArrowLeft, Upload, X, Trash2, Save, PlusCircle } from "lucide-react";

export const Route = createFileRoute("/episodes/new")({
	component: NewEpisode,
});

type EpisodeFormData = {
	title: string;
};

function NewEpisode() {
	const navigate = useNavigate();
	const fileInputRef = useRef<HTMLInputElement>(null);
	const [audioFiles, setAudioFiles] = useState<File[]>([]);
	const [isUploading, setIsUploading] = useState(false);

	const {
		handleSubmit,
		register,
		formState: { errors, isSubmitting },
	} = useForm<EpisodeFormData>();

	const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
		if (e.target.files && e.target.files.length > 0) {
			// Convert FileList to array and append to existing files
			const newFiles = Array.from(e.target.files);
			setAudioFiles((prev) => [...prev, ...newFiles]);
		}
	};

	const removeFile = (index: number) => {
		setAudioFiles((prev) => prev.filter((_, i) => i !== index));
	};

	const onSubmit = async (values: EpisodeFormData) => {
		if (audioFiles.length === 0) {
			toaster.error({
				title: "Missing audio files",
				description: "Please upload at least one audio file for your episode",
			});
			return;
		}

		try {
			setIsUploading(true);

			// Create a loading toast that will be updated when the operation completes
			const uploadPromise = (async () => {
				try {
					const response = await createEpisodeV1EpisodesPost({
						body: {
							title: values.title,
							files: audioFiles,
						},
					});

					if (response.error) {
						if (response.error instanceof Error) {
							throw response.error;
						}
						throw new Error("Failed to create episode");
					}

					// Navigate back to episodes list on success
					navigate({ to: "/" });
				} finally {
					setIsUploading(false);
				}
			})();

			// Use the promise-based toast for better UX
			toaster.promise(uploadPromise, {
				loading: {
					title: "Uploading episode",
					description:
						"Please wait while your episode files are being uploaded",
				},
				success: {
					title: "Episode created",
					description: "Your episode has been created successfully",
				},
				error: (err) => ({
					title: "Error",
					description:
						err instanceof Error ? err.message : "Failed to create episode",
				}),
			});
		} catch (err) {
			setIsUploading(false);
			toaster.error({
				title: "Error",
				description:
					err instanceof Error ? err.message : "Failed to create episode",
			});
		}
	};

	const triggerFileInput = () => {
		if (fileInputRef.current) {
			fileInputRef.current.click();
		}
	};

	const getTotalSize = () => {
		return (
			audioFiles.reduce((total, file) => total + file.size, 0) / (1024 * 1024)
		);
	};

	return (
		<Box p={4}>
			<Flex justifyContent="space-between" alignItems="center" mb={4}>
				<Heading size="lg">Create New Episode</Heading>
				<Button onClick={() => navigate({ to: "/" })}>
					<ArrowLeft size={16} /> Back to Episodes
				</Button>
			</Flex>

			<Card.Root variant="outline" p={4}>
				<form onSubmit={handleSubmit(onSubmit)}>
					<VStack gap={4} align="stretch">
						<Field.Root invalid={!!errors.title}>
							<Field.Label>
								Episode Title
								<Field.RequiredIndicator />
							</Field.Label>
							<Input id="title" placeholder="Enter episode title" />
						</Field.Root>

						<Field.Root invalid={audioFiles.length === 0}>
							<Field.Label>
								Audio Files
								<Field.RequiredIndicator />
							</Field.Label>

							<input
								type="file"
								ref={fileInputRef}
								onChange={handleFileChange}
								accept="audio/*"
								multiple
								style={{ display: "none" }}
							/>

							<Flex direction="column" gap={2}>
								<Button
									onClick={triggerFileInput}
									variant="outline"
									width="full"
									height="40px"
								>
									{audioFiles.length > 0 ? (
										<>
											<PlusCircle size={16} /> Add More Audio Files
										</>
									) : (
										<>
											<Upload size={16} /> Upload Audio Files
										</>
									)}
								</Button>

								{audioFiles.length > 0 ? (
									<>
										<Text fontSize="sm" fontWeight="medium" mb={2}>
											{audioFiles.length} file(s) selected - Total size:{" "}
											{getTotalSize().toFixed(2)} MB
										</Text>
										<SimpleGrid columns={3} gap={2}>
											{audioFiles.map((file, index) => (
												<Box
													key={`audio-file-${file.name}`}
													p={2}
													borderWidth="1px"
													borderRadius="md"
													borderStyle="solid"
													borderColor="gray.200"
													mb={2}
												>
													<Flex
														justifyContent="space-between"
														alignItems="center"
														height="100%"
													>
														<Box>
															<Text fontSize="sm" fontWeight="medium">
																{file.name}
															</Text>
															<Text fontSize="xs" color="gray.500">
																{(file.size / (1024 * 1024)).toFixed(2)} MB
															</Text>
														</Box>
														<Button
															size="sm"
															variant="ghost"
															colorScheme="red"
															onClick={() => removeFile(index)}
														>
															<Trash2 size={14} /> Remove
														</Button>
													</Flex>
												</Box>
											))}
										</SimpleGrid>
									</>
								) : (
									<Text fontSize="sm" color="gray.500">
										Select audio files to upload (.mp3, .wav, etc.)
									</Text>
								)}
							</Flex>

							{audioFiles.length === 0 && (
								<Field.ErrorText>
									At least one audio file is required
								</Field.ErrorText>
							)}
						</Field.Root>

						<Flex justifyContent="flex-end" mt={4}>
							<Button mr={3} onClick={() => navigate({ to: "/" })}>
								<X size={16} /> Cancel
							</Button>
							<Button
								colorScheme="blue"
								loading={isSubmitting || isUploading}
								type="submit"
								disabled={audioFiles.length === 0}
							>
								<Save size={16} /> Create Episode
							</Button>
						</Flex>
					</VStack>
				</form>
			</Card.Root>
		</Box>
	);
}
