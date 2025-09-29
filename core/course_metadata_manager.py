"""
Course Metadata Management System

This module handles:
- Enhanced categorization system with tags and difficulty levels
- Course relationship mapping (prerequisites, sequences, related content)
- Metadata validation and standardization
- Search optimization with indexed course attributes
- Version control for course updates and revisions
"""

import asyncio
import json
import logging
import re
from datetime import datetime
from typing import Dict, List, Optional, Any, Union, Tuple
from dataclasses import dataclass, asdict
from enum import Enum

from .supabase_client import SupabaseClient
from .redis_state import RedisStateManager as RedisState

logger = logging.getLogger(__name__)

class DifficultyLevel(Enum):
    """Course difficulty levels"""
    BEGINNER = 1
    INTERMEDIATE = 2
    ADVANCED = 3
    EXPERT = 4
    MASTER = 5

class CourseType(Enum):
    """Course content types"""
    TUTORIAL = "tutorial"
    MASTERCLASS = "masterclass"
    GAME_ANALYSIS = "game_analysis"
    OPENING_THEORY = "opening_theory"
    ENDGAME_STUDY = "endgame_study"
    TACTICAL_TRAINING = "tactical_training"
    STRATEGY_GUIDE = "strategy_guide"
    HISTORICAL_STUDY = "historical_study"

class RelationType(Enum):
    """Course relationship types"""
    PREREQUISITE = "prerequisite"
    SEQUENCE = "sequence"
    RELATED = "related"
    CONTINUATION = "continuation"
    ALTERNATIVE = "alternative"

@dataclass
class CourseMetadata:
    """Enhanced course metadata structure"""
    course_id: str
    title: str
    description: str
    category: Optional[str] = None
    subcategory: Optional[str] = None
    tags: List[str] = None
    difficulty_level: DifficultyLevel = DifficultyLevel.BEGINNER
    course_type: CourseType = CourseType.TUTORIAL
    estimated_duration: Optional[int] = None  # in minutes
    skill_level_required: List[str] = None
    learning_objectives: List[str] = None
    chess_rating_range: Optional[Tuple[int, int]] = None  # (min_rating, max_rating)
    language: str = "en"
    version: int = 1
    created_at: datetime = None
    updated_at: datetime = None
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = []
        if self.skill_level_required is None:
            self.skill_level_required = []
        if self.learning_objectives is None:
            self.learning_objectives = []
        if self.created_at is None:
            self.created_at = datetime.utcnow()
        if self.updated_at is None:
            self.updated_at = datetime.utcnow()

@dataclass
class CourseRelationship:
    """Course relationship structure"""
    source_course_id: str
    target_course_id: str
    relation_type: RelationType
    weight: float = 1.0  # Relationship strength (0.0 to 1.0)
    description: Optional[str] = None
    created_at: datetime = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()

class CourseMetadataManager:
    """Manages course metadata, relationships, and search optimization"""
    
    def __init__(self, supabase_client: SupabaseClient, redis_client: RedisState):
        self.supabase = supabase_client
        self.redis = redis_client
        
        # Metadata validation rules
        self.valid_categories = {
            "Opening Theory": ["King's Pawn", "Queen's Pawn", "English Opening", "French Defense", "Sicilian Defense", "Other Openings"],
            "Middlegame": ["Strategy", "Tactics", "Positional Play", "Attack & Defense", "Pawn Structure"],
            "Endgame": ["Basic Endgames", "Complex Endgames", "Theoretical Endgames", "Practical Endgames"],
            "Master Classes": ["GM Analysis", "Famous Games", "Tournament Preparation", "Style Studies"],
            "Training": ["Puzzle Collections", "Exercise Sets", "Practice Positions", "Drill Sessions"],
            "History": ["Chess History", "Player Biographies", "Tournament History", "Chess Evolution"],
            "Analysis": ["Game Analysis", "Position Analysis", "Opening Analysis", "Study Collections"]
        }
        
        self.common_tags = [
            # Opening tags
            "e4", "d4", "Nf3", "c4", "sicilian", "french", "caro-kann", "king-indian",
            "queen-gambit", "english", "ruy-lopez", "italian", "scotch",
            
            # Middlegame tags
            "tactics", "strategy", "attack", "defense", "sacrifice", "positional",
            "initiative", "piece-activity", "pawn-structure", "weak-squares",
            
            # Endgame tags
            "king-pawn", "rook-endgame", "bishop-endgame", "knight-endgame",
            "queen-endgame", "opposite-bishops", "same-color-bishops",
            
            # General tags
            "beginner", "intermediate", "advanced", "master-level", "theoretical",
            "practical", "exercises", "analysis", "annotated", "video-course"
        ]
        
        # Search index configuration
        self.search_weights = {
            "title": 1.0,
            "description": 0.8,
            "tags": 0.9,
            "category": 0.7,
            "learning_objectives": 0.6
        }
    
    async def create_course_metadata(self, metadata: CourseMetadata) -> Dict[str, Any]:
        """Create comprehensive course metadata with validation"""
        try:
            # Validate metadata
            validation_result = await self._validate_metadata(metadata)
            if not validation_result["valid"]:
                return {
                    "success": False,
                    "errors": validation_result["errors"],
                    "message": "Metadata validation failed"
                }
            
            # Normalize and enhance metadata
            normalized_metadata = await self._normalize_metadata(metadata)
            
            # Generate search keywords
            search_keywords = await self._generate_search_keywords(normalized_metadata)
            
            # Insert course metadata
            result = await self.supabase.execute_command(
                """
                INSERT INTO course_metadata (
                    course_id, title, description, category, subcategory, 
                    difficulty_level, course_type, estimated_duration,
                    language, version, search_keywords, created_at, updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                RETURNING course_id
                """,
                normalized_metadata.course_id, normalized_metadata.title, normalized_metadata.description,
                normalized_metadata.category, normalized_metadata.subcategory,
                normalized_metadata.difficulty_level.value, normalized_metadata.course_type.value,
                normalized_metadata.estimated_duration, normalized_metadata.language,
                normalized_metadata.version, search_keywords,
                normalized_metadata.created_at, normalized_metadata.updated_at
            )
            
            if not result:
                return {
                    "success": False,
                    "message": "Failed to create course metadata"
                }
            
            # Insert tags
            if normalized_metadata.tags:
                for tag in normalized_metadata.tags:
                    await self.supabase.execute_command(
                        "INSERT INTO course_tags (course_id, tag, weight) VALUES ($1, $2, $3)",
                        normalized_metadata.course_id, tag.lower().strip(), 1.0
                    )
            
            # Insert learning objectives
            if normalized_metadata.learning_objectives:
                for i, objective in enumerate(normalized_metadata.learning_objectives):
                    await self.supabase.execute_command(
                        "INSERT INTO course_learning_objectives (course_id, objective, order_index) VALUES ($1, $2, $3)",
                        normalized_metadata.course_id, objective, i + 1
                    )
            
            # Insert skill requirements
            if normalized_metadata.skill_level_required:
                for skill in normalized_metadata.skill_level_required:
                    await self.supabase.execute_command(
                        "INSERT INTO course_skill_requirements (course_id, skill_name) VALUES ($1, $2)",
                        normalized_metadata.course_id, skill
                    )
            
            # Cache metadata for quick access
            await self._cache_metadata(normalized_metadata)
            
            # Update search index
            await self._update_search_index(normalized_metadata, search_keywords)
            
            logger.info(f"Created metadata for course {normalized_metadata.course_id}")
            
            return {
                "success": True,
                "course_id": normalized_metadata.course_id,
                "metadata": asdict(normalized_metadata),
                "search_keywords": search_keywords
            }
            
        except Exception as e:
            logger.error(f"Failed to create course metadata: {e}")
            return {
                "success": False,
                "message": f"Failed to create metadata: {str(e)}"
            }
    
    async def update_course_metadata(self, course_id: str, updates: Dict[str, Any], 
                                   create_version: bool = True) -> Dict[str, Any]:
        """Update course metadata with optional versioning"""
        try:
            # Get current metadata
            current_metadata = await self.get_course_metadata(course_id)
            if not current_metadata["success"]:
                return current_metadata
            
            current = current_metadata["metadata"]
            
            # Create new version if requested
            if create_version:
                current["version"] += 1
                
                # Archive current version
                await self.supabase.execute_command(
                    """
                    INSERT INTO course_metadata_history (
                        course_id, version, title, description, category, subcategory,
                        difficulty_level, course_type, estimated_duration, language,
                        archived_at
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                    """,
                    course_id, current["version"] - 1, current["title"], current["description"],
                    current["category"], current["subcategory"], current["difficulty_level"],
                    current["course_type"], current["estimated_duration"], current["language"],
                    datetime.utcnow()
                )
            
            # Apply updates
            updated_metadata = CourseMetadata(**{**current, **updates})
            updated_metadata.updated_at = datetime.utcnow()
            
            # Validate updated metadata
            validation_result = await self._validate_metadata(updated_metadata)
            if not validation_result["valid"]:
                return {
                    "success": False,
                    "errors": validation_result["errors"],
                    "message": "Updated metadata validation failed"
                }
            
            # Normalize updated metadata
            normalized_metadata = await self._normalize_metadata(updated_metadata)
            
            # Generate new search keywords
            search_keywords = await self._generate_search_keywords(normalized_metadata)
            
            # Update database
            await self.supabase.execute_command(
                """
                UPDATE course_metadata SET
                    title = $2, description = $3, category = $4, subcategory = $5,
                    difficulty_level = $6, course_type = $7, estimated_duration = $8,
                    language = $9, version = $10, search_keywords = $11, updated_at = $12
                WHERE course_id = $1
                """,
                course_id, normalized_metadata.title, normalized_metadata.description,
                normalized_metadata.category, normalized_metadata.subcategory,
                normalized_metadata.difficulty_level.value, normalized_metadata.course_type.value,
                normalized_metadata.estimated_duration, normalized_metadata.language,
                normalized_metadata.version, search_keywords, normalized_metadata.updated_at
            )
            
            # Update tags if provided
            if "tags" in updates:
                await self.supabase.execute_command("DELETE FROM course_tags WHERE course_id = $1", course_id)
                for tag in normalized_metadata.tags:
                    await self.supabase.execute_command(
                        "INSERT INTO course_tags (course_id, tag, weight) VALUES ($1, $2, $3)",
                        course_id, tag.lower().strip(), 1.0
                    )
            
            # Update learning objectives if provided
            if "learning_objectives" in updates:
                await self.supabase.execute_command("DELETE FROM course_learning_objectives WHERE course_id = $1", course_id)
                for i, objective in enumerate(normalized_metadata.learning_objectives):
                    await self.supabase.execute_command(
                        "INSERT INTO course_learning_objectives (course_id, objective, order_index) VALUES ($1, $2, $3)",
                        course_id, objective, i + 1
                    )
            
            # Update cache
            await self._cache_metadata(normalized_metadata)
            
            # Update search index
            await self._update_search_index(normalized_metadata, search_keywords)
            
            logger.info(f"Updated metadata for course {course_id} (version {normalized_metadata.version})")
            
            return {
                "success": True,
                "course_id": course_id,
                "metadata": asdict(normalized_metadata),
                "version_created": create_version,
                "search_keywords": search_keywords
            }
            
        except Exception as e:
            logger.error(f"Failed to update course metadata: {e}")
            return {
                "success": False,
                "message": f"Failed to update metadata: {str(e)}"
            }
    
    async def get_course_metadata(self, course_id: str, version: Optional[int] = None) -> Dict[str, Any]:
        """Get course metadata with optional version specification"""
        try:
            # Try cache first for current version
            if not version:
                cached_metadata = await self._get_cached_metadata(course_id)
                if cached_metadata:
                    return {
                        "success": True,
                        "metadata": cached_metadata,
                        "source": "cache"
                    }
            
            # Query database
            if version:
                # Get specific version from history
                result = await self.supabase.execute_query(
                    """
                    SELECT * FROM course_metadata_history 
                    WHERE course_id = $1 AND version = $2
                    """,
                    course_id, version
                )
            else:
                # Get current version
                result = await self.supabase.execute_query(
                    "SELECT * FROM course_metadata WHERE course_id = $1",
                    course_id
                )
            
            if not result:
                return {
                    "success": False,
                    "message": "Course metadata not found"
                }
            
            metadata_row = result[0]
            
            # Get associated data
            tags_result = await self.supabase.execute_query(
                "SELECT tag FROM course_tags WHERE course_id = $1 ORDER BY weight DESC",
                course_id
            )
            tags = [row["tag"] for row in tags_result] if tags_result else []
            
            objectives_result = await self.supabase.execute_query(
                "SELECT objective FROM course_learning_objectives WHERE course_id = $1 ORDER BY order_index",
                course_id
            )
            objectives = [row["objective"] for row in objectives_result] if objectives_result else []
            
            skills_result = await self.supabase.execute_query(
                "SELECT skill_name FROM course_skill_requirements WHERE course_id = $1",
                course_id
            )
            skills = [row["skill_name"] for row in skills_result] if skills_result else []
            
            # Construct metadata object
            metadata = {
                "course_id": metadata_row["course_id"],
                "title": metadata_row["title"],
                "description": metadata_row["description"],
                "category": metadata_row["category"],
                "subcategory": metadata_row["subcategory"],
                "tags": tags,
                "difficulty_level": metadata_row["difficulty_level"],
                "course_type": metadata_row["course_type"],
                "estimated_duration": metadata_row["estimated_duration"],
                "skill_level_required": skills,
                "learning_objectives": objectives,
                "language": metadata_row["language"],
                "version": metadata_row["version"],
                "created_at": metadata_row["created_at"],
                "updated_at": metadata_row["updated_at"]
            }
            
            # Cache current version
            if not version:
                await self._cache_metadata_dict(course_id, metadata)
            
            return {
                "success": True,
                "metadata": metadata,
                "source": "database"
            }
            
        except Exception as e:
            logger.error(f"Failed to get course metadata for {course_id}: {e}")
            return {
                "success": False,
                "message": f"Failed to get metadata: {str(e)}"
            }
    
    async def create_course_relationship(self, relationship: CourseRelationship) -> Dict[str, Any]:
        """Create relationship between courses"""
        try:
            # Validate relationship
            validation_result = await self._validate_relationship(relationship)
            if not validation_result["valid"]:
                return {
                    "success": False,
                    "errors": validation_result["errors"],
                    "message": "Relationship validation failed"
                }
            
            # Insert relationship
            await self.supabase.execute_command(
                """
                INSERT INTO course_relationships (
                    source_course_id, target_course_id, relation_type, weight, description, created_at
                ) VALUES ($1, $2, $3, $4, $5, $6)
                """,
                relationship.source_course_id, relationship.target_course_id,
                relationship.relation_type.value, relationship.weight,
                relationship.description, relationship.created_at
            )
            
            # Update relationship cache
            await self._update_relationship_cache(relationship)
            
            logger.info(f"Created relationship: {relationship.source_course_id} -> {relationship.target_course_id} ({relationship.relation_type.value})")
            
            return {
                "success": True,
                "relationship": asdict(relationship)
            }
            
        except Exception as e:
            logger.error(f"Failed to create course relationship: {e}")
            return {
                "success": False,
                "message": f"Failed to create relationship: {str(e)}"
            }
    
    async def get_course_relationships(self, course_id: str, 
                                     relation_types: List[RelationType] = None) -> Dict[str, Any]:
        """Get all relationships for a course"""
        try:
            # Build query conditions
            if relation_types:
                type_conditions = " OR ".join([f"relation_type = '{rt.value}'" for rt in relation_types])
                where_clause = f"(source_course_id = $1 OR target_course_id = $1) AND ({type_conditions})"
            else:
                where_clause = "source_course_id = $1 OR target_course_id = $1"
            
            # Query relationships
            relationships_result = await self.supabase.execute_query(
                f"""
                SELECT cr.*, 
                       source_meta.title as source_title,
                       target_meta.title as target_title
                FROM course_relationships cr
                JOIN course_metadata source_meta ON cr.source_course_id = source_meta.course_id
                JOIN course_metadata target_meta ON cr.target_course_id = target_meta.course_id
                WHERE {where_clause}
                ORDER BY cr.weight DESC
                """,
                course_id
            )
            
            if not relationships_result:
                return {
                    "success": True,
                    "relationships": {
                        "outgoing": [],
                        "incoming": [],
                        "total": 0
                    }
                }
            
            # Organize relationships
            outgoing = []
            incoming = []
            
            for rel in relationships_result:
                rel_data = {
                    "course_id": rel["target_course_id"] if rel["source_course_id"] == course_id else rel["source_course_id"],
                    "title": rel["target_title"] if rel["source_course_id"] == course_id else rel["source_title"],
                    "relation_type": rel["relation_type"],
                    "weight": rel["weight"],
                    "description": rel["description"]
                }
                
                if rel["source_course_id"] == course_id:
                    outgoing.append(rel_data)
                else:
                    incoming.append(rel_data)
            
            return {
                "success": True,
                "relationships": {
                    "outgoing": outgoing,
                    "incoming": incoming,
                    "total": len(relationships_result)
                }
            }
            
        except Exception as e:
            logger.error(f"Failed to get course relationships for {course_id}: {e}")
            return {
                "success": False,
                "message": f"Failed to get relationships: {str(e)}"
            }
    
    async def search_courses_advanced(self, query: str, filters: Dict[str, Any] = None, 
                                    limit: int = 20, offset: int = 0) -> Dict[str, Any]:
        """Advanced course search with metadata filtering"""
        try:
            # Parse search query
            search_terms = self._parse_search_query(query)
            
            # Build search conditions
            search_conditions = []
            search_params = []
            param_index = 1
            
            # Full-text search on multiple fields
            if search_terms["text"]:
                search_conditions.append(f"""
                    (
                        to_tsvector('english', title) @@ plainto_tsquery('english', ${param_index}) OR
                        to_tsvector('english', description) @@ plainto_tsquery('english', ${param_index}) OR
                        search_keywords ILIKE '%' || ${param_index} || '%'
                    )
                """)
                search_params.append(search_terms["text"])
                param_index += 1
            
            # Apply filters
            if filters:
                if filters.get("category"):
                    search_conditions.append(f"category = ${param_index}")
                    search_params.append(filters["category"])
                    param_index += 1
                
                if filters.get("difficulty_level"):
                    if isinstance(filters["difficulty_level"], list):
                        placeholders = ",".join([f"${i}" for i in range(param_index, param_index + len(filters["difficulty_level"]))])
                        search_conditions.append(f"difficulty_level IN ({placeholders})")
                        search_params.extend(filters["difficulty_level"])
                        param_index += len(filters["difficulty_level"])
                    else:
                        search_conditions.append(f"difficulty_level = ${param_index}")
                        search_params.append(filters["difficulty_level"])
                        param_index += 1
                
                if filters.get("course_type"):
                    search_conditions.append(f"course_type = ${param_index}")
                    search_params.append(filters["course_type"])
                    param_index += 1
                
                if filters.get("duration_range"):
                    min_duration, max_duration = filters["duration_range"]
                    search_conditions.append(f"estimated_duration BETWEEN ${param_index} AND ${param_index + 1}")
                    search_params.extend([min_duration, max_duration])
                    param_index += 2
                
                if filters.get("tags"):
                    # Search for courses with any of the specified tags
                    tags_placeholder = ",".join([f"${i}" for i in range(param_index, param_index + len(filters["tags"]))])
                    search_conditions.append(f"""
                        EXISTS (
                            SELECT 1 FROM course_tags ct 
                            WHERE ct.course_id = cm.course_id 
                            AND ct.tag IN ({tags_placeholder})
                        )
                    """)
                    search_params.extend(filters["tags"])
                    param_index += len(filters["tags"])
            
            # Build final query
            where_clause = " AND ".join(search_conditions) if search_conditions else "1=1"
            
            # Calculate relevance score
            relevance_score = "1.0"
            if search_terms["text"]:
                relevance_score = f"""
                    (
                        CASE WHEN title ILIKE '%{search_terms["text"]}%' THEN 2.0 ELSE 0.0 END +
                        CASE WHEN description ILIKE '%{search_terms["text"]}%' THEN 1.0 ELSE 0.0 END +
                        CASE WHEN search_keywords ILIKE '%{search_terms["text"]}%' THEN 1.5 ELSE 0.0 END
                    )
                """
            
            # Main search query
            search_query = f"""
                SELECT cm.*, 
                       {relevance_score} as relevance_score,
                       COALESCE(cs.total_enrollments, 0) as popularity_score
                FROM course_metadata cm
                LEFT JOIN course_statistics cs ON cm.course_id = cs.course_id
                WHERE {where_clause}
                ORDER BY relevance_score DESC, popularity_score DESC, cm.updated_at DESC
                LIMIT ${param_index} OFFSET ${param_index + 1}
            """
            
            search_params.extend([limit, offset])
            
            # Execute search
            results = await self.supabase.execute_query(search_query, *search_params)
            
            # Get total count
            count_query = f"""
                SELECT COUNT(*) as total
                FROM course_metadata cm
                WHERE {where_clause}
            """
            
            count_result = await self.supabase.execute_query(count_query, *search_params[:-2])  # Exclude limit and offset
            total_results = count_result[0]["total"] if count_result else 0
            
            # Enhance results with tags and relationships
            enhanced_results = []
            for result in results:
                # Get tags
                tags_result = await self.supabase.execute_query(
                    "SELECT tag FROM course_tags WHERE course_id = $1 ORDER BY weight DESC LIMIT 10",
                    result["course_id"]
                )
                tags = [row["tag"] for row in tags_result] if tags_result else []
                
                enhanced_result = dict(result)
                enhanced_result["tags"] = tags
                enhanced_results.append(enhanced_result)
            
            return {
                "success": True,
                "results": enhanced_results,
                "total_results": total_results,
                "query": query,
                "filters_applied": filters or {},
                "pagination": {
                    "limit": limit,
                    "offset": offset,
                    "has_more": offset + limit < total_results
                }
            }
            
        except Exception as e:
            logger.error(f"Failed to search courses: {e}")
            return {
                "success": False,
                "message": f"Search failed: {str(e)}"
            }
    
    async def get_course_recommendations(self, course_id: str, limit: int = 10) -> Dict[str, Any]:
        """Get course recommendations based on relationships and metadata similarity"""
        try:
            # Get course metadata
            metadata_result = await self.get_course_metadata(course_id)
            if not metadata_result["success"]:
                return metadata_result
            
            source_metadata = metadata_result["metadata"]
            
            # Get related courses from relationships
            relationships = await self.get_course_relationships(course_id)
            related_courses = []
            
            if relationships["success"]:
                for rel in relationships["relationships"]["outgoing"]:
                    if rel["relation_type"] in ["related", "continuation", "sequence"]:
                        related_courses.append({
                            "course_id": rel["course_id"],
                            "title": rel["title"],
                            "score": rel["weight"] * 2.0,  # Higher weight for explicit relationships
                            "reason": f"Explicitly related ({rel['relation_type']})"
                        })
            
            # Find courses with similar metadata
            similarity_query = """
                SELECT cm.course_id, cm.title, cm.category, cm.difficulty_level,
                       (
                           CASE WHEN cm.category = $2 THEN 0.8 ELSE 0.0 END +
                           CASE WHEN cm.difficulty_level = $3 THEN 0.6 ELSE 0.0 END +
                           CASE WHEN cm.course_type = $4 THEN 0.4 ELSE 0.0 END
                       ) as similarity_score
                FROM course_metadata cm
                WHERE cm.course_id != $1
                  AND (cm.category = $2 OR cm.difficulty_level = $3 OR cm.course_type = $4)
                ORDER BY similarity_score DESC
                LIMIT $5
            """
            
            similar_courses_result = await self.supabase.execute_query(
                similarity_query,
                course_id, source_metadata["category"], source_metadata["difficulty_level"],
                source_metadata["course_type"], limit
            )
            
            # Add similar courses to recommendations
            for course in similar_courses_result:
                if course["similarity_score"] > 0:
                    related_courses.append({
                        "course_id": course["course_id"],
                        "title": course["title"],
                        "score": course["similarity_score"],
                        "reason": "Similar content and difficulty"
                    })
            
            # Find courses with shared tags
            if source_metadata["tags"]:
                tags_placeholder = ",".join(["$" + str(i) for i in range(2, 2 + len(source_metadata["tags"]))])
                shared_tags_query = f"""
                    SELECT cm.course_id, cm.title, COUNT(ct.tag) as shared_tags
                    FROM course_metadata cm
                    JOIN course_tags ct ON cm.course_id = ct.course_id
                    WHERE cm.course_id != $1 AND ct.tag IN ({tags_placeholder})
                    GROUP BY cm.course_id, cm.title
                    HAVING COUNT(ct.tag) > 0
                    ORDER BY shared_tags DESC
                    LIMIT {limit // 2}
                """
                
                shared_tags_result = await self.supabase.execute_query(
                    shared_tags_query, course_id, *source_metadata["tags"]
                )
                
                for course in shared_tags_result:
                    score = (course["shared_tags"] / len(source_metadata["tags"])) * 1.2
                    related_courses.append({
                        "course_id": course["course_id"],
                        "title": course["title"],
                        "score": score,
                        "reason": f"Shares {course['shared_tags']} tag(s)"
                    })
            
            # Remove duplicates and sort by score
            unique_recommendations = {}
            for rec in related_courses:
                course_id_key = rec["course_id"]
                if course_id_key not in unique_recommendations or rec["score"] > unique_recommendations[course_id_key]["score"]:
                    unique_recommendations[course_id_key] = rec
            
            final_recommendations = sorted(
                unique_recommendations.values(),
                key=lambda x: x["score"],
                reverse=True
            )[:limit]
            
            return {
                "success": True,
                "source_course_id": course_id,
                "recommendations": final_recommendations,
                "total_found": len(final_recommendations)
            }
            
        except Exception as e:
            logger.error(f"Failed to get course recommendations for {course_id}: {e}")
            return {
                "success": False,
                "message": f"Failed to get recommendations: {str(e)}"
            }
    
    async def _validate_metadata(self, metadata: CourseMetadata) -> Dict[str, Any]:
        """Validate course metadata"""
        errors = []
        
        # Title validation
        if not metadata.title or len(metadata.title.strip()) < 5:
            errors.append("Title must be at least 5 characters long")
        elif len(metadata.title) > 200:
            errors.append("Title must be 200 characters or less")
        
        # Description validation
        if not metadata.description or len(metadata.description.strip()) < 20:
            errors.append("Description must be at least 20 characters long")
        elif len(metadata.description) > 2000:
            errors.append("Description must be 2000 characters or less")
        
        # Category validation
        if metadata.category and metadata.category not in self.valid_categories:
            errors.append(f"Invalid category. Choose from: {', '.join(self.valid_categories.keys())}")
        
        # Subcategory validation
        if metadata.subcategory and metadata.category:
            valid_subcategories = self.valid_categories.get(metadata.category, [])
            if metadata.subcategory not in valid_subcategories:
                errors.append(f"Invalid subcategory for {metadata.category}. Choose from: {', '.join(valid_subcategories)}")
        
        # Tags validation
        if metadata.tags:
            if len(metadata.tags) > 20:
                errors.append("Maximum 20 tags allowed")
            
            for tag in metadata.tags:
                if len(tag.strip()) < 2:
                    errors.append(f"Tag '{tag}' is too short (minimum 2 characters)")
                elif len(tag.strip()) > 30:
                    errors.append(f"Tag '{tag}' is too long (maximum 30 characters)")
        
        # Duration validation
        if metadata.estimated_duration and (metadata.estimated_duration < 1 or metadata.estimated_duration > 1440):
            errors.append("Estimated duration must be between 1 and 1440 minutes (24 hours)")
        
        # Learning objectives validation
        if metadata.learning_objectives and len(metadata.learning_objectives) > 10:
            errors.append("Maximum 10 learning objectives allowed")
        
        return {
            "valid": len(errors) == 0,
            "errors": errors
        }
    
    async def _validate_relationship(self, relationship: CourseRelationship) -> Dict[str, Any]:
        """Validate course relationship"""
        errors = []
        
        # Check if courses exist
        source_exists = await self.supabase.execute_query(
            "SELECT 1 FROM course_metadata WHERE course_id = $1",
            relationship.source_course_id
        )
        
        target_exists = await self.supabase.execute_query(
            "SELECT 1 FROM course_metadata WHERE course_id = $1",
            relationship.target_course_id
        )
        
        if not source_exists:
            errors.append(f"Source course {relationship.source_course_id} does not exist")
        
        if not target_exists:
            errors.append(f"Target course {relationship.target_course_id} does not exist")
        
        # Check for self-reference
        if relationship.source_course_id == relationship.target_course_id:
            errors.append("Course cannot have a relationship with itself")
        
        # Check weight range
        if not (0.0 <= relationship.weight <= 1.0):
            errors.append("Relationship weight must be between 0.0 and 1.0")
        
        # Check for duplicate relationship
        existing = await self.supabase.execute_query(
            """
            SELECT 1 FROM course_relationships 
            WHERE source_course_id = $1 AND target_course_id = $2 AND relation_type = $3
            """,
            relationship.source_course_id, relationship.target_course_id, relationship.relation_type.value
        )
        
        if existing:
            errors.append("This relationship already exists")
        
        return {
            "valid": len(errors) == 0,
            "errors": errors
        }
    
    async def _normalize_metadata(self, metadata: CourseMetadata) -> CourseMetadata:
        """Normalize and enhance metadata"""
        # Clean title and description
        metadata.title = metadata.title.strip()
        metadata.description = metadata.description.strip()
        
        # Normalize tags
        if metadata.tags:
            normalized_tags = []
            for tag in metadata.tags:
                clean_tag = re.sub(r'[^a-zA-Z0-9\-_]', '', tag.lower().strip())
                if clean_tag and clean_tag not in normalized_tags:
                    normalized_tags.append(clean_tag)
            metadata.tags = normalized_tags
        
        # Suggest additional tags based on content
        suggested_tags = await self._suggest_tags(metadata)
        if suggested_tags and metadata.tags:
            for tag in suggested_tags[:3]:  # Add up to 3 suggested tags
                if tag not in metadata.tags:
                    metadata.tags.append(tag)
        
        return metadata
    
    async def _suggest_tags(self, metadata: CourseMetadata) -> List[str]:
        """Suggest tags based on title and description content"""
        suggested = []
        content = f"{metadata.title} {metadata.description}".lower()
        
        for tag in self.common_tags:
            if tag in content and tag not in (metadata.tags or []):
                suggested.append(tag)
        
        return suggested[:5]  # Return top 5 suggestions
    
    async def _generate_search_keywords(self, metadata: CourseMetadata) -> str:
        """Generate search keywords for optimized searching"""
        keywords = []
        
        # Add title words
        title_words = re.findall(r'\b\w+\b', metadata.title.lower())
        keywords.extend(title_words)
        
        # Add description words (key terms)
        description_words = re.findall(r'\b\w{4,}\b', metadata.description.lower())  # 4+ character words
        keywords.extend(description_words[:20])  # Limit to 20 key words
        
        # Add category and subcategory
        if metadata.category:
            keywords.append(metadata.category.lower().replace(' ', '-'))
        if metadata.subcategory:
            keywords.append(metadata.subcategory.lower().replace(' ', '-'))
        
        # Add tags
        if metadata.tags:
            keywords.extend(metadata.tags)
        
        # Add difficulty level
        keywords.append(f"level-{metadata.difficulty_level.value}")
        keywords.append(metadata.difficulty_level.name.lower())
        
        # Add course type
        keywords.append(metadata.course_type.value.replace('_', '-'))
        
        # Remove duplicates and create searchable string
        unique_keywords = list(set(keywords))
        return ' '.join(unique_keywords[:50])  # Limit total keywords
    
    def _parse_search_query(self, query: str) -> Dict[str, Any]:
        """Parse search query into structured components"""
        # Basic implementation - can be enhanced with more sophisticated parsing
        return {
            "text": query.strip(),
            "filters": {},  # Could extract filters like "category:opening" from query
            "operators": []  # Could extract AND, OR, NOT operators
        }
    
    async def _cache_metadata(self, metadata: CourseMetadata):
        """Cache course metadata for quick access"""
        try:
            cache_key = f"course_metadata:{metadata.course_id}"
            await self.redis.set(
                cache_key,
                json.dumps(asdict(metadata), default=str),
                ex=3600  # Cache for 1 hour
            )
        except Exception as e:
            logger.error(f"Failed to cache metadata: {e}")
    
    async def _cache_metadata_dict(self, course_id: str, metadata_dict: Dict):
        """Cache course metadata dictionary"""
        try:
            cache_key = f"course_metadata:{course_id}"
            await self.redis.set(
                cache_key,
                json.dumps(metadata_dict, default=str),
                ex=3600
            )
        except Exception as e:
            logger.error(f"Failed to cache metadata dict: {e}")
    
    async def _get_cached_metadata(self, course_id: str) -> Optional[Dict]:
        """Get cached course metadata"""
        try:
            cache_key = f"course_metadata:{course_id}"
            cached_data = await self.redis.get(cache_key)
            if cached_data:
                return json.loads(cached_data)
        except Exception as e:
            logger.error(f"Failed to get cached metadata: {e}")
        return None
    
    async def _update_search_index(self, metadata: CourseMetadata, keywords: str):
        """Update search index for optimized searching"""
        try:
            # This would integrate with a search engine like Elasticsearch
            # For now, we store search-optimized data in the database
            pass
        except Exception as e:
            logger.error(f"Failed to update search index: {e}")
    
    async def _update_relationship_cache(self, relationship: CourseRelationship):
        """Update relationship cache"""
        try:
            # Cache bidirectional relationships
            source_key = f"course_relationships:{relationship.source_course_id}"
            target_key = f"course_relationships:{relationship.target_course_id}"
            
            # This is a simplified implementation
            # In practice, you'd maintain more sophisticated relationship caching
            pass
        except Exception as e:
            logger.error(f"Failed to update relationship cache: {e}")