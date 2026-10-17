from dataclasses import dataclass

from tags.core.tag import App, Tag, TagAlias, TagEdge


@dataclass
class TagDag:
    tags: list[Tag]
    edges: list[TagEdge]
    aliases: list[TagAlias]
    apps: list[App]
