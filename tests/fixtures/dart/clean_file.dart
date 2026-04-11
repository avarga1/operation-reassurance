// REASSURE: expect clean (no god file, no god class, no soc violation)
//
// One widget. One concern. Correct.
// This file must NOT trigger any SOLID/SoC flags.
// If it does, the analyzer has a false positive.

import 'package:flutter/material.dart';

class UserAvatar extends StatelessWidget {
  final String name;
  final String? imageUrl;

  const UserAvatar({super.key, required this.name, this.imageUrl});

  @override
  Widget build(BuildContext context) {
    return CircleAvatar(
      backgroundImage: imageUrl != null ? NetworkImage(imageUrl!) : null,
      child: imageUrl == null ? Text(_initials()) : null,
    );
  }

  String _initials() {
    final parts = name.trim().split(' ');
    if (parts.length == 1) return parts[0][0].toUpperCase();
    return '${parts.first[0]}${parts.last[0]}'.toUpperCase();
  }
}
