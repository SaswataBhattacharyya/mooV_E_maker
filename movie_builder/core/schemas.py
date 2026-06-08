from pydantic import BaseModel, Field
from typing import Optional


# ── Intake Schemas ──────────────────────────────────────────────

class ProjectIntake(BaseModel):
    project_id: str = ""
    title: str = ""
    project_type: str = "Movie / Short Film"
    raw_story: str = ""
    genre: str = "Drama"
    custom_genre: str = ""
    tone: str = "Emotional"
    custom_tone: str = ""
    visual_style: str = "Photorealistic"
    target_format: str = "Feature Film (90-120 min)"
    language: str = "English"
    style_references: str = ""
    things_to_avoid: str = ""
    allow_web_research: bool = False

    def to_dict(self) -> dict:
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict) -> "ProjectIntake":
        # Map old field names
        field_map = {"genre": "genre", "visual_style": "visual_style", "target_format": "target_format"}
        return cls(**{k: v for k, v in data.items()})


class ExpandedStory(BaseModel):
    project_id: str = ""
    title: str = ""
    project_type: str = ""
    genre: str = ""
    logline: str = ""
    short_synopsis: str = ""
    expanded_story: str = ""
    themes: list[str] = []
    ending: str = ""
    story_summary_for_context: str = ""

    def to_dict(self) -> dict:
        return self.model_dump()


# ── Character Schemas ──────────────────────────────────────────────

class CharacterIndexItem(BaseModel):
    character_id: str = ""
    position: int = 1
    name: str = ""
    role: str = Field(default="supporting", description="protagonist / antagonist / supporting / minor")
    short_description: str = ""
    story_purpose: str = ""
    appears_in_units: list[str] = []
    status: str = "draft"

    def to_dict(self) -> dict:
        return self.model_dump()


class CharacterIndex(BaseModel):
    characters: list[CharacterIndexItem] = []

    def to_dict(self) -> dict:
        return self.model_dump()


class CharacterDetail(BaseModel):
    character_id: str = ""
    name: str = ""
    role: str = ""
    age_range: str = ""
    gender_presentation: str = ""
    personality: str = ""
    backstory: str = ""
    motivation: str = ""
    fear: str = ""
    arc: str = ""
    speech_style: str = ""
    physical_description: str = ""
    costume: str = ""
    expression_notes: str = ""
    pose_notes: str = ""
    visual_prompt: str = ""
    book_voice: str = ""
    inner_conflict: str = ""
    pov_style: str = ""
    audio_voice_profile: str = ""
    accent: str = ""
    pace: str = ""
    emotion_range: str = ""
    summary_for_context: str = ""

    def to_dict(self) -> dict:
        return self.model_dump()


# ── World / Style Bible Schemas ──────────────────────────────────────

class LocationItem(BaseModel):
    location_id: str = ""
    name: str = ""
    short_description: str = ""
    visual_notes: str = ""
    story_use: str = ""


class WorldBible(BaseModel):
    world_rules: list[str] = []
    locations: list[LocationItem] = []
    visual_style: str = ""
    color_palette: list[str] = []
    mood: str = ""
    genre_conventions: list[str] = []
    reference_style_notes: str = ""


# ── Structure Index Schemas

class SceneIndexItem(BaseModel):
    scene_id: str = ""
    position: int = 1
    title: str = ""
    short_description: str = ""
    scene_purpose: str = ""
    primary_characters: list[str] = []
    status: str = "draft"


class ActItem(BaseModel):
    act_id: str = ""
    position: int = 1
    title: str = ""
    short_description: str = ""
    scenes: list[SceneIndexItem] = []

    def to_dict(self) -> dict:
        return {
            "act_id": self.act_id,
            "position": self.position,
            "title": self.title,
            "short_description": self.short_description,
            "scenes": [s.model_dump() for s in self.scenes],
        }


class StructureIndex(BaseModel):
    project_type: str = ""
    items: list[ActItem] = []  # Acts for movie; Chapters for comic/episodes

    def to_dict(self) -> dict:
        return {
            "project_type": self.project_type,
            "items": [item.to_dict() for item in self.items],
        }


class ComicChapter(BaseModel):
    chapter_id: str = ""
    position: int = 1
    title: str = ""
    short_description: str = ""
    pages: list["ComicPage"] = []

    def to_dict(self) -> dict:
        return {
            "chapter_id": self.chapter_id,
            "position": self.position,
            "title": self.title,
            "short_description": self.short_description,
            "pages": [p.model_dump() for p in self.pages],
        }


class ComicPage(BaseModel):
    page_id: str = ""
    position: int = 1
    short_description: str = ""
    panel_count_target: int = 5
    page_purpose: str = ""
    status: str = "draft"


# ── Unit Schemas

class MovieSceneBlock(BaseModel):
    scene_id: str = ""
    scene_summary: str = ""
    subscenes: list[str] = []
    characters_present: list[str] = []
    dialogue: str = ""
    action_blocking: str = ""
    background_location: str = ""
    props: str = ""
    costume_makeup: str = ""
    camera_notes: str = ""
    lighting_notes: str = ""
    sound_effects: str = ""
    music: str = ""
    vfx_sfx: str = ""
    storyboard_prompts: str = ""
    continuity_notes: str = ""

    def to_dict(self) -> dict:
        return self.model_dump()


class ComicPageBlock(BaseModel):
    page_id: str = ""
    chapter_id: str = ""
    panels: list["ComicPanelBlock"] = []
    page_level_notes: str = ""

    def to_dict(self) -> dict:
        return {
            "page_id": self.page_id,
            "chapter_id": self.chapter_id,
            "panels": [p.model_dump() for p in self.panels],
            "page_level_notes": self.page_level_notes,
        }


class ComicPanelBlock(BaseModel):
    panel_id: str = ""
    panel_size: str = ""
    visual_description: str = ""
    characters_visible: list[str] = []
    pose_expression: str = ""
    background: str = ""
    caption: str = ""
    speech_bubbles: str = ""
    sfx_text: str = ""
    image_prompt: str = ""

    def to_dict(self) -> dict:
        return self.model_dump()


class BookSectionBlock(BaseModel):
    section_id: str = ""
    chapter_id: str = ""
    section_summary: str = ""
    chapter_beats: list[str] = []
    pov: str = ""
    setting: str = ""
    characters_present: list[str] = []
    emotional_arc: str = ""
    section_draft: str = ""
    continuity_notes: str = ""

    def to_dict(self) -> dict:
        return self.model_dump()


# ── Continuity Schemas

class ContinuityIssue(BaseModel):
    issue_id: str = ""
    severity: str = "low"  # low, medium, high, critical
    affected_ids: list[str] = []
    problem: str = ""
    suggested_fix: str = ""
    status: str = "open"

    def to_dict(self) -> dict:
        return self.model_dump()


class ContinuityReport(BaseModel):
    project_id: str = ""
    issues: list[ContinuityIssue] = []

    def to_dict(self) -> dict:
        return self.model_dump()


# ── Circular import fix ──────────────────────────────────────
ComicChapter.model_rebuild()
ComicPage.model_rebuild()
