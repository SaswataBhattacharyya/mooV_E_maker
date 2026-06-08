"""Tests for core.schemas."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestSchemas:
    def test_intake_defaults(self):
        from core.schemas import ProjectIntake
        p = ProjectIntake()
        assert p.genre == "Drama" and p.tone == "Emotional"
    
    def test_intake_custom(self):
        from core.schemas import ProjectIntake
        p = ProjectIntake(title="TM", genre="Sci-fi")
        assert p.title == "TM" and p.genre == "Sci-fi"
    
    def test_intake_to_dict(self):
        from core.schemas import ProjectIntake
        d = ProjectIntake(title="T").to_dict()
        assert d["title"] == "T"
    
    def test_expanded_story(self):
        from core.schemas import ExpandedStory
        s = ExpandedStory(logline="L", themes=["a", "b"])
        assert len(s.themes) == 2
    
    def test_character_index(self):
        from core.schemas import CharacterIndex, CharacterIndexItem
        ci = CharacterIndex(characters=[CharacterIndexItem(name="Homer")])
        d = ci.to_dict()
        assert len(d["characters"]) == 1
    
    def test_character_detail(self):
        from core.schemas import CharacterDetail
        cd = CharacterDetail(character_id="char_001")
        assert cd.character_id == "char_001"
    
    def test_structure_index_to_dict(self):
        from core.schemas import StructureIndex, ActItem, SceneIndexItem
        scene = SceneIndexItem(scene_id="scn_001", title="S1")
        act = ActItem(act_id="act_001", title="Act 1", scenes=[scene])
        si = StructureIndex(project_type="Movie / Short Film", items=[act])
        d = si.to_dict()
        assert d["project_type"] == "Movie / Short Film" and len(d["items"]) == 1
    
    def test_comic_schema(self):
        from core.schemas import ComicChapter, ComicPage, ComicPanelBlock
        panel = ComicPanelBlock(panel_id="p1", visual_description="A dark alley")
        page = ComicPage(page_id="pg1")
        chap = ComicChapter(chapter_id="ch1", pages=[page])
        d = chap.model_dump()
        assert len(d["pages"]) == 1
        # ComicPageBlock has panels; ComicPage does not (that's a different class)
    
    def test_movie_scene_block(self):
        from core.schemas import MovieSceneBlock
        msb = MovieSceneBlock(scene_id="scene_001", scene_summary="Homer enters")
        d = msb.to_dict()
        assert d["scene_id"] == "scene_001"
    
    def test_continuity_issue(self):
        from core.schemas import ContinuityIssue, ContinuityReport
        ci = ContinuityIssue(issue_id="cont_001", severity="high", problem="Missing char", status="open")
        r = ContinuityReport(project_id="p1", issues=[ci])
        d = r.to_dict()
        assert len(d["issues"]) == 1
    
    def test_book_section_block(self):
        from core.schemas import BookSectionBlock
        bs = BookSectionBlock(section_id="sec_001", pov="first-person")
        d = bs.to_dict()
        assert d["pov"] == "first-person"
